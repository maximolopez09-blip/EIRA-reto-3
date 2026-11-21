"""Preproceso de fotos y escaneos de los formatos de EIRA.

1. Corrige la iluminación (sombras, fondo gris) y endereza la hoja si se ve sobre una mesa.
2. Localiza las etiquetas impresas con Tesseract y las empareja con la plantilla del formato; con eso
   reconoce de qué formato y página se trata y calcula la transformación que lleva la foto a la plantilla.
3. Rectifica la página y recorta cada espacio a llenar (sin la raya ni el marco impresos).
"""
import os
import re
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from .config import DATOS, TESSDATA
from .formularios import PLANTILLAS
from .quality import norm

ESCALA = 4.0  # píxeles por punto en la página rectificada (288 ppp)
MIN_ANCLAS = 12


@dataclass
class Pagina:
    formato: str
    indice: int
    imagen: np.ndarray  # página rectificada en gris, ESCALA px/pt
    anclas: int
    recortes: dict = field(default_factory=dict)  # nombre de campo -> recorte en gris (None si está vacío)


def iluminar(gris: np.ndarray) -> np.ndarray:
    """Divide entre el fondo estimado: quita sombras y deja el papel blanco."""
    k = max(15, (min(gris.shape) // 40) | 1)
    fondo = cv2.medianBlur(cv2.dilate(gris, np.ones((k // 2 | 1, k // 2 | 1), np.uint8)), k if k % 2 else k + 1)
    plano = cv2.divide(gris, fondo, scale=255)
    lo, hi = np.percentile(plano, (1, 60))
    return np.clip((plano.astype(np.float32) - lo) * 255 / max(1, hi - lo), 0, 255).astype(np.uint8)


def encuadrar(bgr: np.ndarray) -> np.ndarray:
    """Si la hoja se ve completa como un cuadrilátero claro sobre un fondo, la recorta y quita la perspectiva."""
    gris = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    f = 800 / max(gris.shape)
    ch = cv2.GaussianBlur(cv2.resize(gris, None, fx=f, fy=f, interpolation=cv2.INTER_AREA), (0, 0), 3)
    _, bw = cv2.threshold(ch, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    cont, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cont:
        return bgr
    c = max(cont, key=cv2.contourArea)
    area = cv2.contourArea(c) / bw.size
    quad = cv2.approxPolyDP(cv2.convexHull(c), 0.02 * cv2.arcLength(c, True), True)
    if len(quad) != 4 or not 0.3 < area < 0.97:
        return bgr
    q = quad.reshape(4, 2).astype(np.float32) / f
    s, d = q.sum(1), q[:, 0] - q[:, 1]
    q = np.float32([q[s.argmin()], q[d.argmax()], q[s.argmax()], q[d.argmin()]])  # ↖ ↗ ↘ ↙
    w = int(max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3])))
    h = int(max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1])))
    if min(w, h) < 0.4 * min(gris.shape):
        return bgr
    M = cv2.getPerspectiveTransform(q, np.float32([[0, 0], [w, 0], [w, h], [0, h]]))
    return cv2.warpPerspective(bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _clave(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(t))


def palabras_impresas(gris: np.ndarray, tesseract: str) -> list[tuple[str, float, float]]:
    """Palabras que Tesseract lee en la página, con su centro (x, y) en píxeles."""
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = tesseract
    if (TESSDATA / "spa.traineddata").exists():
        os.environ["TESSDATA_PREFIX"] = str(TESSDATA)
    f = min(3.0, max(1.0, 2600 / max(gris.shape)))  # el texto impreso es pequeño: se amplía antes de leer
    img = cv2.resize(gris, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC) if f > 1.05 else gris
    try:
        d = pytesseract.image_to_data(Image.fromarray(img), lang="spa", config="--psm 11", output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractError as e:
        if "spa" in str(e) or "traineddata" in str(e):
            raise RuntimeError("Tesseract no tiene instalado el idioma español (spa.traineddata).") from e
        raise RuntimeError(f"Tesseract no pudo leer el documento: {e}") from e
    f = f if f > 1.05 else 1.0
    return [(_clave(t), (x + w / 2) / f, (y + h / 2) / f) for t, x, y, w, h in zip(d["text"], d["left"], d["top"], d["width"], d["height"])
            if len(_clave(t)) >= 4]


def _anclas(pag: dict) -> dict[str, list[tuple[float, float]]]:
    res = {}
    for w in pag["palabras"]:
        k = _clave(w["t"])
        if len(k) >= 4:
            x0, y0, x1, y1 = w["caja"]
            res.setdefault(k, []).append(((x0 + x1) / 2, (y0 + y1) / 2))
    return {k: v for k, v in res.items() if len(v) <= 3}


ANCLAS = {(clave, i): _anclas(pag) for clave, pl in PLANTILLAS.items() for i, pag in enumerate(pl["paginas"])}


def emparejar(palabras, anclas, tolerancia: float):
    """Homografía plantilla (pt) -> imagen (px) a partir de las palabras impresas que coinciden. Devuelve (H, src, dst) o None."""
    src, dst = [], []
    for k, x, y in palabras:
        for ax, ay in anclas.get(k, ()):
            src.append((ax, ay))
            dst.append((x, y))
    if len(src) < MIN_ANCLAS:
        return None
    src, dst = np.float32(src), np.float32(dst)
    H, m = cv2.findHomography(src, dst, cv2.RANSAC, tolerancia, maxIters=5000, confidence=0.999)
    if H is None or int(m.sum()) < MIN_ANCLAS:
        return None
    m = m.ravel().astype(bool)
    return H, src[m], dst[m]


_BLANCOS = {}


def _blanco(formato: str, indice: int, e: float) -> np.ndarray:
    """Página del formato sin llenar, en gris, a `e` px/pt."""
    if (formato, indice, e) not in _BLANCOS:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(DATOS / "formatos" / PLANTILLAS[formato]["archivo"]))
        _BLANCOS[(formato, indice, e)] = np.asarray(pdf[indice].render(scale=e, grayscale=True).to_pil().convert("L"))
        pdf.close()
    return _BLANCOS[(formato, indice, e)]


def emparejar_dibujo(hoja: np.ndarray):
    """Respaldo cuando la letra impresa no se alcanza a leer: compara la hoja ya encuadrada con el dibujo
    (rayas, marcos y bloques de texto) de cada formato en blanco y la ajusta con ECC.
    Devuelve (parecido, formato, indice, H plantilla pt -> px de `hoja`) o None."""
    mejor = None
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    for (formato, indice) in ANCLAS:
        pag = PLANTILLAS[formato]["paginas"][indice]
        if abs(hoja.shape[0] / hoja.shape[1] - pag["alto"] / pag["ancho"]) > 0.12 * pag["alto"] / pag["ancho"]:
            continue
        for giro in (False, True):
            h = cv2.rotate(hoja, cv2.ROTATE_180) if giro else hoja
            W = np.eye(3, dtype=np.float32)
            cc = 0.0
            try:
                for e in (0.5, 1.0, 2.0):  # de grueso a fino
                    ref = _blanco(formato, indice, e)
                    mov = cv2.resize(h, (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_AREA)
                    S = np.diag([2.0, 2.0, 1.0]).astype(np.float32) if e > 0.5 else np.eye(3, dtype=np.float32)
                    W = S @ W @ np.linalg.inv(S)
                    cc, W = cv2.findTransformECC(255 - ref, 255 - mov, W.astype(np.float32), cv2.MOTION_HOMOGRAPHY, crit, None, 7)
            except cv2.error:
                continue
            if mejor is None or cc > mejor[0]:
                # plantilla (pt) -> ref (px, e=2) -> mov -> hoja (posiblemente girada)
                A = np.diag([h.shape[1] / ref.shape[1], h.shape[0] / ref.shape[0], 1.0]) @ W @ np.diag([2.0, 2.0, 1.0])
                if giro:
                    A = np.array([[-1, 0, hoja.shape[1] - 1], [0, -1, hoja.shape[0] - 1], [0, 0, 1.0]]) @ A
                mejor = (cc, formato, indice, A)
    return mejor if mejor and mejor[0] > 0.3 else None


def _desfase(pag_img: np.ndarray, blanco: np.ndarray, caja, alcance: int = 20, borde: int = 110):
    """Desfase local (px) entre la página rectificada y el formato en blanco alrededor de una caja."""
    H, W = blanco.shape
    x0, y0, x1, y1 = [int(v * ESCALA) for v in caja]
    a0, b0, a1, b1 = max(0, x0 - borde), max(0, y0 - borde), min(W, x1 + borde), min(H, y1 + borde)
    A0, B0, A1, B1 = max(0, a0 - alcance), max(0, b0 - alcance), min(W, a1 + alcance), min(H, b1 + alcance)
    ref = cv2.GaussianBlur(255 - blanco[b0:b1, a0:a1], (0, 0), 2)
    zona = cv2.GaussianBlur(255 - pag_img[B0:B1, A0:A1], (0, 0), 2)
    if ref.std() < 2 or zona.shape[0] < ref.shape[0] or zona.shape[1] < ref.shape[1]:
        return 0, 0
    r = cv2.matchTemplate(zona, ref, cv2.TM_CCOEFF_NORMED)
    _, cc, _, (mx, my) = cv2.minMaxLoc(r)
    return (mx - (a0 - A0), my - (b0 - B0)) if cc > 0.25 else (0, 0)


def recortar(pag_img: np.ndarray, blanco: np.ndarray, campo: dict):
    """Recorte de lo escrito a mano en un campo: sin lo impreso y ajustado a la tinta. None si está vacío."""
    H, W = pag_img.shape
    dx, dy = _desfase(pag_img, blanco, campo["caja"])
    x0, y0, x1, y1 = [int(v * ESCALA) for v in campo["caja"]]
    x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
    mx, my = int(7 * ESCALA), int(6 * ESCALA)  # la letra suele salirse del espacio
    a0, b0, a1, b1 = max(0, x0 - mx), max(0, y0 - my), min(W, x1 + mx), min(H, y1 + my)
    if a1 - a0 < 8 or b1 - b0 < 8:
        return None
    rec = pag_img[b0:b1, a0:a1].copy()
    # lo impreso (rayas, marcos, etiquetas vecinas) se borra con el formato en blanco como máscara
    imp = np.full(rec.shape, 255, np.uint8)
    u0, v0 = a0 - dx, b0 - dy
    su0, sv0, su1, sv1 = max(0, u0), max(0, v0), min(W, u0 + rec.shape[1]), min(H, v0 + rec.shape[0])
    if su1 > su0 and sv1 > sv0:
        imp[sv0 - v0:sv1 - v0, su0 - u0:su1 - u0] = blanco[sv0:sv1, su0:su1]
    k = 5 if campo["tipo"] in ("codigo", "casillas") else 7  # en las casillas la letra queda pegada al marco
    masc = cv2.dilate((imp < 190).astype(np.uint8), np.ones((k, k), np.uint8))
    oscuro = (rec < 140).astype(np.uint8)
    tinta = (oscuro > 0) & (masc == 0)
    tinta = tinta.astype(np.uint8)
    # los trazos cortados por una raya impresa se vuelven a unir
    tinta = cv2.morphologyEx(tinta, cv2.MORPH_CLOSE, np.ones((11, 3), np.uint8))
    n, etq, est, cen = cv2.connectedComponentsWithStats(tinta, connectivity=8)
    cx0, cy0, cx1, cy1 = x0 - a0, y0 - b0, x1 - a0, y1 - b0
    alto = cy1 - cy0
    sirve = np.zeros(n, bool)
    for i in range(1, n):
        x, y, w, h, area = est[i]
        if area < 14:
            continue
        ix = max(0, min(x + w, cx1) - max(x, cx0)) / w  # parte del trazo dentro del espacio del campo
        iy = max(0, min(y + h, cy1 + alto * 0.15) - max(y, cy0 - alto * 0.15)) / h
        toca_borde = x <= 1 or y <= 1 or x + w >= rec.shape[1] - 1 or y + h >= rec.shape[0] - 1
        sirve[i] = ix >= 0.5 and iy >= 0.6 and not (toca_borde and ix * iy < 0.8)
    # las motas del escáner son trazos diminutos y aislados; un punto o un acento solo cuenta junto a un trazo de verdad
    grande = sirve & (est[:, 2:4].max(axis=1) >= 4 * ESCALA)
    if est[grande, cv2.CC_STAT_AREA].sum() < 40:
        return None
    cerca = cv2.dilate(grande[etq].astype(np.uint8), np.ones((int(10 * ESCALA), int(12 * ESCALA)), np.uint8))
    for i in np.nonzero(sirve & ~grande)[0]:
        sirve[i] = cerca[int(cen[i][1]), int(cen[i][0])] > 0
    ys, xs = np.nonzero(sirve[etq])
    m = 10
    p0, q0, p1, q1 = max(0, xs.min() - m), max(0, ys.min() - m), min(rec.shape[1], xs.max() + m), min(rec.shape[0], ys.max() + m)
    mia = sirve[etq].astype(np.uint8)
    puente = cv2.morphologyEx(mia, cv2.MORPH_CLOSE, np.ones((15, 3), np.uint8)) > 0
    rec[(cv2.dilate(mia, np.ones((9, 9), np.uint8)) == 0) | ((masc > 0) & ~puente)] = 255
    return rec[q0:q1, p0:p1]


def _rectificar(gris, H, pag):
    S = np.diag([ESCALA, ESCALA, 1.0])
    tam = (int(pag["ancho"] * ESCALA), int(pag["alto"] * ESCALA))
    return cv2.warpPerspective(gris, S @ np.linalg.inv(H), tam, flags=cv2.INTER_CUBIC, borderValue=255)


def leer_pagina(img: Image.Image, tesseract: str | None) -> Pagina | None:
    """Reconoce el formato, rectifica la página y recorta sus campos. None si no es un formato conocido."""
    bgr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    mejor = None
    hoja = encuadrar(bgr)
    for intento in ((hoja, bgr) if hoja is not bgr else (bgr,)) if tesseract else ():
        gris = iluminar(cv2.cvtColor(intento, cv2.COLOR_BGR2GRAY))
        for giro in (None, cv2.ROTATE_180, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
            g = gris if giro is None else cv2.rotate(gris, giro)
            palabras = palabras_impresas(g, tesseract)
            for clave, anclas in ANCLAS.items():
                r = emparejar(palabras, anclas, tolerancia=max(g.shape) * 0.006)
                if r and (mejor is None or len(r[1]) > mejor[0]):
                    mejor = (len(r[1]), clave, r[0], g)
            if mejor and mejor[0] >= 2 * MIN_ANCLAS:
                break
            if len(palabras) < 15 and giro is None and len(_clave("".join(k for k, _, _ in palabras))) < 60:
                break  # página sin texto legible: girarla no ayuda
        if mejor and mejor[0] >= 2 * MIN_ANCLAS:
            break
    if not mejor:  # letra impresa ilegible (o sin Tesseract): se compara el dibujo del formato
        gris = iluminar(cv2.cvtColor(hoja, cv2.COLOR_BGR2GRAY))
        r = emparejar_dibujo(gris)
        if not r:
            return None
        mejor = (0, (r[1], r[2]), r[3], gris)
    n, (formato, indice), H, gris = mejor
    pag = PLANTILLAS[formato]["paginas"][indice]
    recta = _rectificar(gris, H, pag)
    # Segunda pasada sobre la página ya derecha: más etiquetas localizadas y un ajuste fino por zonas.
    r = tesseract and emparejar([(k, x / ESCALA, y / ESCALA) for k, x, y in palabras_impresas(recta, tesseract)], ANCLAS[(formato, indice)], tolerancia=6.0)
    if r and len(r[1]) >= max(MIN_ANCLAS, n * 0.8):
        recta = _rectificar(recta, np.diag([ESCALA, ESCALA, 1.0]) @ r[0], pag)
        n = len(r[1])
    res = Pagina(formato, indice, recta, n)
    blanco = _blanco(formato, indice, ESCALA)[:recta.shape[0], :recta.shape[1]]
    for c in pag["campos"]:
        res.recortes[c["nombre"]] = recortar(recta, blanco, c)
    return res
