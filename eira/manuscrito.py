"""Lectura de lo escrito a mano en cada campo ya recortado (ver `lectura.py`) y armado del registro.

Motor: RapidOCR (modelos PP-OCR sobre ONNX Runtime, gratuitos y locales). Si no está instalado se usa Tesseract,
que lee mucho peor la letra manuscrita. Cada valor lleva una confianza de 0 a 1 para saber qué revisar a mano.
"""
import os
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from rapidfuzz import fuzz, process

from .config import ALIAS_MUNICIPIO, ATENCION, MUNICIPIOS_CONOCIDOS
from .formularios import PLANTILLAS
from .quality import norm

CONFIANZA_MIN = 0.6
CONFIANZA_NOMBRE = 0.97
# letras que el motor confunde con cifras cuando el campo solo admite números
A_CIFRA = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "i": "1", "|": "1", "!": "1", "L": "1", "n": "11",
                         "Z": "2", "z": "2", "S": "5", "s": "5", "B": "8", "g": "9", "q": "9", "G": "6", "b": "6", "T": "7", "A": "4"})
ENTIDADES = ["Jalisco", "Michoacán", "Colima", "Zacatecas", "Nayarit", "Guanajuato", "Oaxaca", "Guerrero", "Veracruz", "Puebla",
             "Chiapas", "Sinaloa", "Sonora", "Durango", "Hidalgo", "Morelos", "Tabasco", "Yucatán", "Querétaro", "Tlaxcala",
             "Campeche", "Coahuila", "Chihuahua", "Nuevo León", "Tamaulipas", "San Luis Potosí", "Aguascalientes", "Baja California",
             "Baja California Sur", "Quintana Roo", "Ciudad de México", "Estado de México"]
ENTRADA_MNIST = float(os.environ.get("EIRA_MNIST", "255"))
_motor = None


def motor():
    """RapidOCR (solo reconocimiento) o None si no está instalado."""
    global _motor
    if _motor is None:
        try:
            from rapidocr import RapidOCR

            _motor = RapidOCR(params={"Global.log_level": "error"})
        except Exception:
            _motor = False
    return _motor or None


_cifra = None


def cifra(rec: np.ndarray, validas: list[str]) -> tuple[str, float] | None:
    """Clasifica un recorte con una sola cifra (red entrenada con MNIST) entre las cifras válidas. None si no se puede."""
    global _cifra
    if _cifra is None:
        try:
            import onnxruntime as ort

            _cifra = ort.InferenceSession(str(Path(__file__).parent / "modelos" / "mnist-12.onnx"), providers=["CPUExecutionProvider"])
        except Exception:
            _cifra = False
    ys, xs = np.nonzero(rec < 140)
    if not _cifra or not len(xs) or not validas:
        return None
    g = 255 - rec[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = g.shape
    if w > 1.15 * h:  # más ancho que alto: no es una sola cifra
        return None
    f = 20 / max(h, w)
    g = cv2.resize(g, (max(1, round(w * f)), max(1, round(h * f))), interpolation=cv2.INTER_AREA)
    lienzo = np.zeros((28, 28), np.float32)
    y, x = (28 - g.shape[0]) // 2, (28 - g.shape[1]) // 2
    lienzo[y:y + g.shape[0], x:x + g.shape[1]] = g
    lienzo *= 255 / max(1.0, lienzo.max())
    z = _cifra.run(None, {_cifra.get_inputs()[0].name: lienzo[None, None] / ENTRADA_MNIST})[0][0]
    z = np.array([z[int(v)] for v in validas], np.float64)
    p = np.exp(z - z.max())
    p /= p.sum()
    return validas[int(p.argmax())], float(p.max())


def _lienzo(rec: np.ndarray) -> np.ndarray:
    """Recorte con margen blanco y altura suficiente para el motor."""
    f = max(1.0, 64 / rec.shape[0]) if rec.shape[0] < 64 else min(1.0, 96 / rec.shape[0])
    if abs(f - 1) > 0.05:
        rec = cv2.resize(rec, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC if f > 1 else cv2.INTER_AREA)
    return cv2.copyMakeBorder(rec, 10, 10, 14, 14, cv2.BORDER_CONSTANT, value=255)


def reconocer(recortes: list[np.ndarray], tesseract: str | None = None) -> list[tuple[str, float]]:
    """Texto y confianza de cada recorte."""
    m = motor()
    res = []
    for rec in recortes:
        img = _lienzo(rec)
        if m:
            r = m(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), use_det=False, use_cls=False, use_rec=True)
            res.append((" ".join(r.txts), float(min(r.scores))) if r.txts else ("", 0.0))
        elif tesseract:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = tesseract
            d = pytesseract.image_to_data(Image.fromarray(img), lang="spa", config="--psm 7", output_type=pytesseract.Output.DICT)
            pal = [(t, float(c)) for t, c in zip(d["text"], d["conf"]) if t.strip() and float(c) >= 0]
            res.append((" ".join(t for t, _ in pal), min(c for _, c in pal) / 100) if pal else ("", 0.0))
        else:
            raise RuntimeError("No hay motor de lectura: instala rapidocr (pip install -r requirements.txt) o Tesseract OCR.")
    return res


def _cifras(t: str, extra: str = "") -> str:
    return re.sub(rf"[^0-9{re.escape(extra)}]", "", t.translate(A_CIFRA))


def _catalogo(t: str, opciones: list[str], corte: int = 75):
    """Opción del catálogo más parecida a lo leído, o None."""
    r = process.extractOne(norm(t), {o: norm(o) for o in opciones}, scorer=fuzz.ratio, score_cutoff=corte)
    return r[2] if r else None


def interpretar(campo: dict, t: str, conf: float, rec: np.ndarray | None = None) -> tuple[str, float]:
    """Ajusta lo leído al tipo de campo. Lo que no encaja se devuelve con confianza 0 para revisarlo a mano."""
    tipo, nombre = campo["tipo"], campo["nombre"]
    t = " ".join(re.sub(r"[^\x20-\x7eÁÉÍÓÚÜÑáéíóúüñ°]", "", t).split())
    if not re.search(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", t):  # rayas o manchas, no letra
        return "", 0.0
    if tipo == "codigo":
        v = _cifras(t).lstrip("0") or _cifras(t)
        ops = campo.get("opciones") or {}
        c = cifra(rec, [o for o in ops if len(o) == 1]) if rec is not None else None
        if c and not (v in ops and len(v) > 1):  # una sola cifra en la casilla: decide el clasificador de cifras
            return c[0], c[1] if c[0] == v else c[1] * 0.75
        if v in ops:
            return v, conf
        for cand in (v[:1], v[-1:]):  # restos del marco de la casilla leídos como un «1» de más
            if cand in ops:
                return cand, conf * 0.5
        return v, 0.0
    if tipo == "casillas":
        v = _cifras(t)
        n = campo.get("n")
        return v, conf if not n or len(v) == n else conf * 0.5
    if tipo == "folio":
        m = re.search(r"([A-Za-z]{2})\W*([0-9OoIlSsBZz]{3,})", t)
        return (f"{m.group(1).upper()}-{_cifras(m.group(2))}", conf) if m else (t.upper(), 0.0)
    if tipo == "numero":
        if nombre == "talla":
            v = _cifras(t, ".,").replace(",", ".")
            if re.fullmatch(r"[12]\d\d", v):
                v = f"{v[0]}.{v[1:]}"
            return v, conf if re.fullmatch(r"[12]\.\d\d", v) else 0.0
        if nombre == "presion_arterial":
            v = _cifras(t, "/")
            return v, conf if re.fullmatch(r"\d{2,3}/\d{2,3}", v) else 0.0
        if "telefono" in nombre or nombre == "celular":
            v = _cifras(t)
            return (f"{v[:3]} {v[3:6]} {v[6:]}", conf) if len(v) == 10 else (v, 0.0)
        v = _cifras(t)
        lim = {"dia": (1, 31, 2), "mes": (1, 12, 2), "anio": (1900, 2100, 4), "edad": (0, 110, 0)}
        for suf, (lo, hi, ancho) in lim.items():
            if nombre.endswith(suf):
                ok = v.isdigit() and lo <= int(v) <= hi
                return (v.zfill(ancho) if ok and suf != "anio" else v), conf if ok else 0.0
        return v, conf if v else 0.0
    if nombre == "entidad_nacimiento":
        e = _catalogo(t, ENTIDADES)
        return (e, max(conf, 0.9)) if e else (t, conf)
    if nombre == "correo":
        return t.replace(" ", "").lower(), conf if re.fullmatch(r"[\w.+-]+@[\w-]+\.[\w.]+", t.replace(" ", "")) else 0.0
    return t, conf


def municipio(residencia: str):
    """Municipio del catálogo mencionado en la residencia habitual, tolerando errores de lectura."""
    n = norm(residencia)
    for alias, m in ALIAS_MUNICIPIO.items():
        if alias in n:
            return m
    candidatos = {m: norm(m) for m in MUNICIPIOS_CONOCIDOS} | {a: a for a in ALIAS_MUNICIPIO}
    mejor = None
    trozos = [x.strip() for x in re.split(r"[,;]", n) if x.strip()] or [n]
    for trozo in trozos:
        r = process.extractOne(trozo, candidatos, scorer=fuzz.WRatio, score_cutoff=82)
        if r and (mejor is None or r[1] > mejor[1]):
            mejor = r
    if not mejor:
        return None
    return ALIAS_MUNICIPIO.get(mejor[2], mejor[2])


def _fecha(v: dict, pre: str):
    d, m, a = (v.get(f"{pre}_{x}") for x in ("dia", "mes", "anio"))
    return f"{int(d):02d}/{int(m):02d}/{a}" if d and m and a and d.isdigit() and m.isdigit() else None


def leer_formato(paginas: list, tesseract: str | None = None) -> dict:
    """Lee todas las páginas reconocidas de un mismo formato. Devuelve valores, confianzas y los campos del registro."""
    formato = paginas[0].formato
    pl = PLANTILLAS[formato]
    valores, conf = {}, {}
    for pag in paginas:
        campos = {c["nombre"]: c for c in pl["paginas"][pag.indice]["campos"]}
        llenos = [(n, r) for n, r in pag.recortes.items() if r is not None]
        for (n, r), (t, c) in zip(llenos, reconocer([r for _, r in llenos], tesseract)):
            v, c = interpretar(campos[n], t, c, r)
            if v:
                valores[n], conf[n] = v, round(c, 2)
    # los renglones de un mismo campo («residencia#1», «residencia#2»…) se unen
    for n in [n for n in valores if n.endswith("#1")]:
        base = n[:-2]
        partes = sorted((k for k in valores if k.startswith(base + "#")), key=lambda k: int(k.split("#")[1]))
        valores[base] = " ".join(valores[k] for k in partes)
        conf[base] = min(conf[k] for k in partes)
    opciones = {c["nombre"]: c.get("opciones") or {} for p in pl["paginas"] for c in p["campos"]}
    pre_fecha = "atencion" if formato == "mamaria" else "toma"
    campos = dict.fromkeys(["folio", "fecha", "tipo_evento", "programa", "municipio", "nombre", "edad", "servicio", "padecimiento"])
    campos.update(folio=valores.get("folio"), fecha=_fecha(valores, pre_fecha), nombre=valores.get("nombre"), tipo_evento=ATENCION,
                  programa="Detección oportuna", servicio=pl["servicio"],
                  edad=int(valores["edad"]) if valores.get("edad", "").isdigit() else None,
                  municipio=municipio(valores.get("residencia", "")) or (valores.get("residencia#2") or None))
    # El padecimiento solo se transcribe si el formato trae marcado un resultado.
    cod = "birads" if formato == "mamaria" else "diagnostico_citologico"
    if valores.get(cod) in opciones[cod] and conf[cod] > 0:
        campos["padecimiento"] = (f"BIRADS {valores[cod]} - " if formato == "mamaria" else "") + opciones[cod][valores[cod]]
    origen = {"folio": ["folio"], "fecha": [f"{pre_fecha}_{x}" for x in ("dia", "mes", "anio")], "nombre": ["nombre"], "edad": ["edad"],
              "municipio": ["residencia"], "padecimiento": [cod]}
    # En letra corrida la confianza del motor casi no distingue aciertos de errores: el nombre se revisa salvo lectura muy segura.
    dudosos = [k for k, fs in origen.items()
               if campos.get(k) and min(conf.get(f, 0) for f in fs) < (CONFIANZA_NOMBRE if k == "nombre" else CONFIANZA_MIN)]
    if campos["edad"] is not None and not 12 <= campos["edad"] <= 105 and "edad" not in dudosos:
        dudosos.append("edad")
    if campos["municipio"] and not municipio(valores.get("residencia", "")) and "municipio" not in dudosos:
        dudosos.append("municipio")
    return {"formato": formato, "titulo": pl["titulo"], "valores": valores, "confianza": conf, "campos": campos, "dudosos": dudosos,
            "opciones": opciones}
