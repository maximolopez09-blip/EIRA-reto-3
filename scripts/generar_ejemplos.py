"""Genera los ejemplos (todos con datos ficticios) en Datos/ejemplos/.

Los documentos imitan los formatos reales de EIRA llenados a mano y luego mal capturados:
fotos de celular (PNG, con perspectiva, sombras, desenfoque y ruido) y escaneos de baja resolución (PDF).
`valores_esperados.json` guarda lo que se escribió en cada uno, para medir la lectura automática.

Uso:
    python scripts/generar_ejemplos.py                        # regenera Datos/ejemplos/
    python scripts/generar_ejemplos.py --lote 30 --salida D   # lote aleatorio adicional para medir exactitud
"""
import argparse
import io
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eira.config import DATOS, EJEMPLOS  # noqa: E402
from eira.formularios import PLANTILLAS  # noqa: E402

FUENTES = Path(__file__).resolve().parent / "fuentes"
PPP = 300  # resolución a la que se «escribe» antes de degradar
LETRAS = ["Caveat[wght].ttf", "Kalam-Regular.ttf", "PatrickHand-Regular.ttf", "IndieFlower-Regular.ttf", "GloriaHallelujah.ttf",
          "ShadowsIntoLight.ttf", "ReenieBeanie.ttf", "NothingYouCouldDo.ttf", "CoveredByYourGrace.ttf", "GochiHand-Regular.ttf",
          "Handlee-Regular.ttf", "ArchitectsDaughter-Regular.ttf", "Zeyada.ttf", "Mali-Regular.ttf", "Neucha.ttf",
          "ShadowsIntoLightTwo-Regular.ttf", "HomemadeApple-Regular.ttf", "RockSalt-Regular.ttf", "WaitingfortheSunrise.ttf",
          "SwankyandMooMoo.ttf", "Dekko-Regular.ttf", "OvertheRainbow.ttf", "Kalam-Light.ttf"]
TINTAS = [(22, 38, 120), (18, 30, 95), (25, 25, 30), (40, 40, 48), (15, 45, 140), (30, 60, 150)]

NOMBRES = ["María Guadalupe", "Rosa Elena", "Carmen", "Ana Laura", "Leticia", "Verónica", "Silvia", "Patricia", "Juana", "Norma Angélica",
           "Martha Alicia", "Yolanda", "Gabriela", "Irma", "Teresa de Jesús", "Alejandra", "Beatriz", "Esperanza", "Lucía", "Araceli",
           "Blanca Estela", "Josefina", "Mónica", "Claudia Ivette", "Adriana"]
APELLIDOS = ["Hernández", "García", "Martínez", "López", "González", "Rodríguez", "Pérez", "Sánchez", "Ramírez", "Flores", "Gómez",
             "Díaz", "Vázquez", "Chávez", "Núñez", "Ochoa", "Cárdenas", "Michel", "Larios", "Villalvazo", "Barragán", "Contreras",
             "Magaña", "Rentería", "Solís", "Zúñiga", "Preciado", "Figueroa"]
ENTIDADES = ["Jalisco"] * 6 + ["Michoacán", "Colima", "Nayarit", "Guanajuato", "Zacatecas", "Ciudad de México", "Sinaloa", "Oaxaca"]
MUNICIPIOS = ["Sayula", "Tuxpan", "Zapotiltic", "Gómez Farías", "Zapotlán el Grande", "Cd. Guzmán"]
CALLES = ["Hidalgo", "Juárez", "Morelos", "Reforma", "Colón", "Degollado", "Federico del Toro", "Lázaro Cárdenas", "Ramón Corona",
          "Quintanar", "Primero de Mayo", "Abasolo", "Independencia", "Zaragoza", "Ocampo"]
COLONIAS = ["Centro", "Constituyentes", "La Providencia", "San Cayetano", "Solidaridad", "El Nogal", "Las Peñas", "Cruz Roja"]
MOTIVOS = ["Revisión de rutina", "Dolor en mama derecha", "Bolita en seno izquierdo", "Chequeo anual", "Secreción por el pezón",
           "Molestia en la axila", "Control por antecedente familiar", "Dolor en ambas mamas"]
ANTICONCEPTIVOS = ["DIU", "Pastillas", "Implante", "Inyección", "OTB", "Ninguno", "Parche"]
EXPLORACION = ["Mamas simétricas, sin masas palpables", "Nódulo móvil de 1 cm en cuadrante superior externo",
               "Sin adenopatías axilares", "Piel y pezón sin alteraciones", "Dolor leve a la palpación", "Tejido fibroglandular denso"]
ULTRASONIDO = ["Tejido fibroglandular heterogéneo", "Quiste simple de 6 mm en mama izquierda", "Sin lesiones sólidas ni quísticas",
               "Ganglios axilares de aspecto normal", "Nódulo ovalado de bordes definidos", "Conductos sin dilatación",
               "Mama derecha sin alteraciones", "Se sugiere control en seis meses"]
NOTAS = ["Se entrega resultado a la paciente", "Acude con su hija", "Se agenda cita de seguimiento", "Paciente refiere mejoría"]
MEDICOS = ["Dra. Laura Méndez Ruiz", "Dr. Jorge Anaya Soto", "Dra. Paola Rivas Cano", "Dra. Elena Tapia Mora"]
LABORATORIOS = ["Lab. Regional Sur", "Citolab Guzmán", "Laboratorio Estatal", "Lab. San José"]
OTROS_RIESGOS = ["Tabaquismo", "Obesidad", "Terapia hormonal por 3 años", "Sin hijos", "Consumo de alcohol", "Ninguno"]


def persona(rng: random.Random, folio: str, citologia: bool) -> dict:
    """Valores ficticios para un formulario; las claves son los nombres de campo de la plantilla."""
    n = lambda a, b: str(rng.randint(a, b))  # noqa: E731
    edad = rng.randint(25, 72)
    anio = 2026
    dia, mes = rng.randint(1, 28), rng.randint(9, 11)
    fecha = lambda d=None, m=None, a=None: (f"{d or rng.randint(1, 28):02d}", f"{m or rng.randint(1, 12):02d}", str(a or anio))  # noqa: E731
    municipio = rng.choice(MUNICIPIOS)
    tel = lambda: "341 " + n(100, 999) + " " + n(1000, 9999)  # noqa: E731
    v = {"folio": folio, "nombre": f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}",
         "entidad_nacimiento": rng.choice(ENTIDADES), "edad": str(edad), "cartilla": rng.choice("12"),
         "residencia#1": f"{rng.choice(CALLES)} {n(1, 480)}, Col. {rng.choice(COLONIAS)}", "residencia#2": f"{municipio}, Jalisco",
         "afiliacion": n(1, 6)}
    v["nacimiento_dia"], v["nacimiento_mes"], v["nacimiento_anio"] = fecha(a=anio - edad)
    if rng.random() < 0.6:
        v["id"] = "".join(rng.choice("0123456789") for _ in range(10 if citologia else 11))
    if citologia:
        v["toma_dia"], v["toma_mes"], v["toma_anio"] = fecha(dia, mes)
        v["interpretacion_dia"], v["interpretacion_mes"], v["interpretacion_anio"] = fecha(min(28, dia + 5), mes)
        v["ultima_regla_dia"], v["ultima_regla_mes"], v["ultima_regla_anio"] = fecha(rng.randint(1, 28), mes - 1)
        dx, repetir = rng.choice(["1"] * 5 + ["2", "3", "4", "5"]), rng.choice("2222221")
        v.update({"telefono": tel(), "numero_afiliacion": n(10**9, 10**10 - 1), "citologia": n(1, 4), "situacion_ginecoobstetrica": n(1, 9),
                  "inicio_vida_sexual": "1", "inicio_vida_sexual_edad": n(15, 24), "vacunacion_vph": rng.choice("12"),
                  "exploracion": rng.choice("1111245"), "utensilio": n(1, 3), "cedula_toma": n(10**6, 10**7 - 1),
                  "factor_riesgo_1": n(1, 5), "muestra_repetida": "2", "caracteristicas_muestra": "1", "diagnostico_citologico": dx,
                  "numero_citologico": "C-" + n(1000, 9999), "laboratorio": rng.choice(LABORATORIOS), "repetir_estudio": repetir,
                  "cedula_citotecnologo": n(10**6, 10**7 - 1), "revisada_por_patologo": rng.choice("12")})
        if v["vacunacion_vph"] == "1":
            v.update({"vacunacion_vph_edad": n(11, 30), "vph_dosis": n(1, 4)})
        if rng.random() < 0.5:
            v["otros_hallazgos"] = n(1, 14)
        if rng.random() < 0.4:
            v["correo"] = v["nombre"].split()[0].lower().replace("í", "i").replace("ó", "o").replace("á", "a").replace("é", "e") + n(10, 99) + "@gmail.com"
        if repetir == "1":
            v["motivo_repetir"] = n(1, 4)
        if v["revisada_por_patologo"] == "1":
            v["cedula_patologo"] = n(10**6, 10**7 - 1)
        return v
    v["atencion_dia"], v["atencion_mes"], v["atencion_anio"] = fecha(dia, mes)
    v["fum_dia"], v["fum_mes"], v["fum_anio"] = fecha(a=anio if edad < 50 else anio - edad + 49)
    birads = rng.choice("011222233")
    v.update({"talla": f"1.{rng.randint(48, 72)}", "peso": n(48, 92), "presion_arterial": f"{rng.randint(10, 14)}0/{rng.randint(6, 9)}0",
              "glucosa": n(80, 160), "celular": tel(), "motivo_consulta#1": rng.choice(MOTIVOS), "menarca": n(10, 15),
              "familiares_cancer_mamario": rng.choice("7777123"), "anticoncepcion_tipo": rng.choice(ANTICONCEPTIVOS),
              "antecedente_mastografia": rng.choice("12"), "otros_factores_riesgo#1": rng.choice(OTROS_RIESGOS),
              "termografia": rng.choice("12"), "birads": birads, "conducta_a_seguir": {"0": "3", "1": "1", "2": "1", "3": "4"}[birads],
              "responsable_estudio": f"{rng.choice(MEDICOS)} Céd. {n(10**6, 10**7 - 1)}", "notas#1": rng.choice(NOTAS)})
    for i, t in enumerate(rng.sample(EXPLORACION, 2)):
        v[f"exploracion_clinica#{i + 1}"] = t
    for i, t in enumerate(rng.sample(ULTRASONIDO, 3)):
        v[f"ultrasonido#{i + 1}"] = t
    if rng.random() < 0.5:
        v["telefono_fijo"] = tel()
    if v["anticoncepcion_tipo"] != "Ninguno":
        v.update({"anticoncepcion_inicio": n(1995, 2022), "anticoncepcion_tiempo": f"{rng.randint(1, 12)} años"})
    if edad >= 50:
        v["menopausia"] = n(45, 52)
    if v["antecedente_mastografia"] == "1":
        v["ultima_mastografia_dia"], v["ultima_mastografia_mes"], v["ultima_mastografia_anio"] = fecha(a=anio - rng.randint(1, 3))
        v["resultado_ultima_mastografia"] = f"BIRADS {rng.randint(1, 2)}"
    if birads in "03":
        v["motivo_referencia"] = n(1, 4)
    return v


# ---------------------------------------------------------------- escritura a mano


class Mano:
    """Una «persona que escribe»: tipo de letra, tamaño, tinta y pulso propios."""

    def __init__(self, rng: random.Random, letra: str | None = None):
        self.rng = rng
        self.ruta = str(FUENTES / (letra or rng.choice(LETRAS)))
        self.tinta = rng.choice(TINTAS)
        self.altura = rng.uniform(8.6, 10.6)  # altura de las mayúsculas, en puntos
        self.inclinacion = rng.uniform(-0.12, 0.2)
        self.pulso = rng.uniform(0.5, 1.4)
        self.grosor = rng.choice([1, 1, 2])
        self._f = {}

    def fuente(self, alto_pt: float) -> ImageFont.FreeTypeFont:
        px = max(8, round(alto_pt * PPP / 72))
        if px not in self._f:
            f = ImageFont.truetype(self.ruta, 100)
            caja = f.getbbox("HE")
            self._f[px] = ImageFont.truetype(self.ruta, max(8, round(100 * px / max(1, caja[3] - caja[1]))))
        return self._f[px]

    def trazo(self, texto: str, alto_pt: float) -> Image.Image:
        """Una palabra en RGBA, con inclinación, giro y grosor ligeramente distintos cada vez."""
        f = self.fuente(alto_pt * self.rng.uniform(0.93, 1.07))
        x0, y0, x1, y1 = f.getbbox(texto)
        m = 12
        capa = Image.new("L", (x1 - x0 + 2 * m, y1 - y0 + 2 * m), 0)
        ImageDraw.Draw(capa).text((m - x0, m - y0), texto, fill=255, font=f, stroke_width=self.grosor)
        s = self.inclinacion + self.rng.gauss(0, 0.03)
        capa = capa.transform(capa.size, Image.AFFINE, (1, s, -s * capa.height / 2, 0, 1, 0), Image.BICUBIC)
        capa = capa.rotate(self.rng.gauss(0, 1.2 * self.pulso), Image.BICUBIC, expand=True)
        capa = capa.filter(ImageFilter.GaussianBlur(self.rng.uniform(0.5, 0.9)))
        a = np.asarray(capa, dtype=np.float32)
        grano = cv2.GaussianBlur(np.random.default_rng(self.rng.getrandbits(32)).uniform(0.55, 1.0, a.shape).astype(np.float32), (0, 0), 2.5)
        a = np.clip(a * grano * self.rng.uniform(0.92, 1.12), 0, 255).astype(np.uint8)
        rgba = Image.new("RGBA", capa.size, self.tinta + (0,))
        rgba.putalpha(Image.fromarray(a))
        rgba.info["base"] = m + (f.getbbox("H")[3] - y0)  # distancia de arriba a la línea base
        return rgba

    def escribir(self, hoja: Image.Image, texto: str, caja_pt, tipo: str, n: int = 0):
        e = PPP / 72
        x0, y0, x1, y1 = (v * e for v in caja_pt)
        if tipo == "casillas":
            paso = (x1 - x0) / n
            for i, c in enumerate(texto[:n]):
                self._pegar(hoja, [self.trazo(c, min(self.altura, 8.5))], x0 + i * paso, x0 + (i + 1) * paso, y1 - 0.2 * (y1 - y0), centrado=True)
            return
        if tipo == "folio":  # dos celdas: prefijo y número
            pre, _, num = texto.partition("-")
            corte = x0 + (x1 - x0) * 0.51
            alto = min(self.altura, (y1 - y0) / e * 0.6)
            self._pegar(hoja, [self.trazo(pre, alto)], x0, corte, y1 - 0.22 * (y1 - y0), centrado=True)
            self._pegar(hoja, [self.trazo(num, alto)], corte, x1, y1 - 0.22 * (y1 - y0), centrado=True)
            return
        if tipo == "codigo" or (y1 - y0) / e < 13:  # casilla pequeña
            alto = min(self.altura, (y1 - y0) / e * 0.82)  # en las casillas chicas la letra casi toca los bordes
            self._pegar(hoja, [self.trazo(texto, alto)], x0, x1, y1 - 0.12 * (y1 - y0), centrado=True, ancho_max=(x1 - x0) * 0.9)
            return
        base = y1 - 4.2 * e + self.rng.gauss(0, 0.5 * self.pulso) * e
        palabras = [self.trazo(p, self.altura) for p in texto.split()]
        self._pegar(hoja, palabras, x0 + self.rng.uniform(1, 5) * e, x1, base, centrado=(x1 - x0) / e < 45, ancho_max=(x1 - x0) * 0.98)

    def _pegar(self, hoja, palabras, x0, x1, base, centrado=False, ancho_max=None):
        esp = self.altura * PPP / 72 * self.rng.uniform(0.45, 0.65)
        total = sum(p.width - 24 for p in palabras) + esp * (len(palabras) - 1)
        f = min(1.0, (ancho_max or (x1 - x0)) / max(1, total))
        if f < 1:  # no cabe: quien escribe aprieta la letra
            palabras = [self._escala(p, f) for p in palabras]
            esp, total = esp * f, total * f
        x = x0 + ((x1 - x0) - total) / 2 if centrado else x0
        deriva = self.rng.gauss(0, 0.004 * self.pulso)
        for p in palabras:
            y = base + (x - x0) * deriva + self.rng.gauss(0, 1.6 * self.pulso)
            hoja.alpha_composite(p, (max(0, int(x - 12 * f)), max(0, int(y - p.info["base"]))))
            x += p.width - 24 * f + esp * self.rng.uniform(0.8, 1.25)

    @staticmethod
    def _escala(p, f):
        q = p.resize((max(1, int(p.width * f)), max(1, int(p.height * f))), Image.LANCZOS)
        q.info["base"] = p.info["base"] * f
        return q


def llenar(clave: str, valores: dict, mano: Mano) -> list[Image.Image]:
    """Páginas del formato (a PPP) con los valores escritos a mano."""
    pl = PLANTILLAS[clave]
    pdf = pdfium.PdfDocument(str(DATOS / "formatos" / pl["archivo"]))
    hojas = []
    for i, pag in enumerate(pl["paginas"]):
        hoja = pdf[i].render(scale=PPP / 72).to_pil().convert("RGBA")
        for c in pag["campos"]:
            if valores.get(c["nombre"]):
                mano.escribir(hoja, valores[c["nombre"]], c["caja"], c["tipo"], c.get("n", 0))
        hojas.append(hoja.convert("RGB"))
    return hojas


# ---------------------------------------------------------------- captura deficiente


def _jpeg(a: np.ndarray, calidad: int) -> np.ndarray:
    return cv2.imdecode(cv2.imencode(".jpg", a, [cv2.IMWRITE_JPEG_QUALITY, calidad])[1], cv2.IMREAD_UNCHANGED)


def _manchas(rs, alto, ancho, escala, lo, hi):
    """Campo suave de valores entre lo y hi (iluminación desigual, textura)."""
    m = rs.uniform(0, 1, (max(2, alto // escala), max(2, ancho // escala))).astype(np.float32)
    m = cv2.resize(m, (ancho, alto), interpolation=cv2.INTER_CUBIC)
    m = (m - m.min()) / max(1e-6, m.max() - m.min())
    return lo + (hi - lo) * m


def foto(hoja: Image.Image, rng: random.Random, lado: int = 2400, dificultad: float = 1.0) -> Image.Image:
    """Simula una foto de celular: hoja sobre una mesa, en perspectiva, con sombra, desenfoque, ruido y compresión."""
    rs = np.random.default_rng(rng.getrandbits(32))
    a = cv2.cvtColor(np.asarray(hoja), cv2.COLOR_RGB2BGR).astype(np.float32)
    h, w = a.shape[:2]
    a *= _manchas(rs, h, w, 400, 0.93, 1.0)[..., None]  # papel no uniforme
    a = a * np.array(rng.choice([(0.97, 0.98, 1.0), (0.93, 0.97, 1.0), (1.0, 0.99, 0.97)]), dtype=np.float32)
    H = lado
    W = int(lado * rng.uniform(0.7, 0.78))
    fondo = np.empty((H, W, 3), np.float32)
    fondo[:] = rng.choice([(38, 34, 30), (70, 78, 92), (52, 60, 84), (25, 25, 28), (96, 110, 128)])
    fondo *= _manchas(rs, H, W, 300, 0.7, 1.2)[..., None]
    fondo += rs.normal(0, 6, fondo.shape).astype(np.float32)
    # esquinas de la hoja dentro de la foto (perspectiva y giro leves; a veces un borde queda fuera del encuadre)
    esc = min(W / w, H / h) * rng.uniform(0.9, 1.0)
    pw, ph = w * esc, h * esc
    cx, cy = W / 2 + rng.uniform(-0.02, 0.02) * W, H / 2 + rng.uniform(-0.02, 0.02) * H
    ang = np.deg2rad(rng.gauss(0, 2.5 * dificultad))
    rot = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    base = np.array([[-pw / 2, -ph / 2], [pw / 2, -ph / 2], [pw / 2, ph / 2], [-pw / 2, ph / 2]]) @ rot.T + [cx, cy]
    tiron = rng.uniform(0.02, 0.07) * dificultad  # el lado lejano se ve más angosto
    lejos = rng.choice([0, 0, 1])  # 0: borde superior lejos; 1: inferior
    for i in ((0, 1) if lejos == 0 else (3, 2)):
        base[i, 0] += (cx - base[i, 0]) * tiron * 2
        base[i, 1] += (cy - base[i, 1]) * tiron * 0.6
    base += rs.normal(0, 0.008 * W * dificultad, base.shape)
    M = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), np.float32(base))
    hoja_w = cv2.warpPerspective(a, M, (W, H), flags=cv2.INTER_AREA, borderValue=(0, 0, 0))
    masc = cv2.warpPerspective(np.ones((h, w), np.float32), M, (W, H), flags=cv2.INTER_LINEAR)
    sombra = cv2.GaussianBlur(np.roll(masc, (int(0.012 * H), int(0.01 * W)), (0, 1)), (0, 0), 0.012 * H)
    fondo *= (1 - 0.55 * sombra)[..., None]
    img = fondo * (1 - masc[..., None]) + hoja_w * masc[..., None]
    # iluminación: degradado + sombra de quien toma la foto
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = rng.uniform(0, 2 * np.pi)
    grad = ((xx / W - 0.5) * np.cos(d) + (yy / H - 0.5) * np.sin(d))
    luz = 1 - rng.uniform(0.15, 0.4) * dificultad * (grad - grad.min()) / (grad.max() - grad.min())
    sx, sy = rng.uniform(0, W), rng.choice([rng.uniform(-0.1, 0.15), rng.uniform(0.85, 1.1)]) * H
    luz *= 1 - rng.uniform(0.15, 0.35) * dificultad * np.exp(-(((xx - sx) / (0.45 * W)) ** 2 + ((yy - sy) / (0.3 * H)) ** 2))
    img *= luz[..., None] * rng.uniform(0.85, 1.0)
    img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.6, 1.1) * dificultad * lado / 2400)
    if rng.random() < 0.5:  # ligero movimiento
        k = np.zeros((5, 5), np.float32)
        k[2, :] = 1 / 5
        k = cv2.warpAffine(k, cv2.getRotationMatrix2D((2, 2), rng.uniform(0, 180), 1), (5, 5))
        img = cv2.filter2D(img, -1, k / k.sum())
    img += rs.normal(0, rng.uniform(3, 6) * dificultad, img.shape).astype(np.float32)
    img = _jpeg(np.clip(img, 0, 255).astype(np.uint8), rng.randint(45, 70))
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def escaneo(hoja: Image.Image, rng: random.Random, ppp: int = 110) -> Image.Image:
    """Simula un escaneo o fotocopia en baja resolución: gris, torcido, deslavado, con motas y compresión fuerte."""
    rs = np.random.default_rng(rng.getrandbits(32))
    g = cv2.cvtColor(np.asarray(hoja), cv2.COLOR_RGB2GRAY).astype(np.float32)
    h, w = g.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), rng.gauss(0, 1.2), 1.0)
    M[:, 2] += [rng.uniform(-0.01, 0.01) * w, rng.uniform(-0.01, 0.01) * h]
    g = cv2.warpAffine(g, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=255)
    e = ppp / PPP
    g = cv2.resize(g, (int(w * e), int(h * e)), interpolation=cv2.INTER_AREA)
    h, w = g.shape
    lo, hi = rng.uniform(40, 80), rng.uniform(225, 245)  # tinta deslavada, fondo grisáceo
    g = lo + (hi - lo) * (g / 255) ** rng.uniform(0.8, 1.3)
    g *= _manchas(rs, h, w, 120, 0.94, 1.0)
    g[:, : int(0.03 * w)] *= np.linspace(0.6, 1, int(0.03 * w), dtype=np.float32)  # sombra del lomo
    g = cv2.GaussianBlur(g, (0, 0), rng.uniform(0.4, 0.7))
    g += rs.normal(0, rng.uniform(3, 7), g.shape).astype(np.float32)
    motas = rs.uniform(0, 1, g.shape)
    g[motas < 0.0006] = rng.uniform(20, 90)
    g[motas > 0.9996] = 250
    return Image.fromarray(_jpeg(np.clip(g, 0, 255).astype(np.uint8), rng.randint(30, 50)))


def a_pdf(paginas: list[Image.Image], ruta: Path, ppp: int):
    paginas[0].save(ruta, "PDF", resolution=ppp, save_all=True, append_images=paginas[1:])


# ---------------------------------------------------------------- ejemplos


def excel(ruta: Path):
    filas = [
        ("AT-301", "02/10/2026", "Zapotiltic", "Norma Beltrán Ruiz", 61, "Revisión mamaria", "", "Atención"),
        ("AT-302", "03/10/2026", "Sayula", "Silvia Pérez Ramos", 44, "Toma de citología", "Cervicitis", "Atención"),
        ("AT-303", "06/10/2026", "Tuxpan", "Teresa Navaro Flores", 57, "Revisión mamaria", "", "Atención"),
        ("AT-304", "08/10/2026", "", "Leticia Gómez Arias", 39, "Toma de citología", "", "Atención"),
        ("AT-305", "28/11/2026", "Gómez Farías", "Irma Solís Vega", 50, "Revisión mamaria", "", "Cita agendada"),
        ("AT-306", "09/10/2026", "Zapotlán el Grande", "Paola Rentería Cruz", 33, "Revisión mamaria", "", "Atención"),
    ]
    cols = ["Folio", "Fecha", "Municipio de residencia", "Nombre completo", "Edad", "Servicio", "Padecimiento", "tipo_registro"]
    frame = pd.DataFrame(filas, columns=cols)
    frame.insert(5, "Programa", "Detección oportuna")
    frame.to_excel(ruta, index=False, sheet_name="Registro jornada")


# (archivo, formato, captura, folio, letra)
EJEMPLOS_FIJOS = [
    ("mamaria_foto.png", "mamaria", "foto", "AT-201", "Kalam-Regular.ttf"),
    ("mamaria_escaneo.pdf", "mamaria", "escaneo", "AT-202", "PatrickHand-Regular.ttf"),
    ("citologia_foto.png", "citologia", "foto", "AT-203", "Caveat[wght].ttf"),
    ("citologia_escaneo.pdf", "citologia", "escaneo", "AT-204", "Handlee-Regular.ttf"),
]


def documento(ruta: Path, clave: str, captura: str, valores: dict, rng: random.Random, letra: str | None = None):
    hojas = llenar(clave, valores, Mano(rng, letra))
    if captura == "foto":  # una imagen por página; la primera (la que identifica a la paciente) lleva el nombre pedido
        for i, hj in enumerate(hojas):
            foto(hj, rng).save(ruta if i == 0 else ruta.with_name(f"{ruta.stem}_pagina{i + 1}{ruta.suffix}"))
    else:
        a_pdf([escaneo(hj, rng) for hj in hojas], ruta, 110)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lote", type=int, default=0, help="número de documentos aleatorios adicionales")
    ap.add_argument("--salida", type=Path, default=None, help="carpeta del lote (por omisión Datos/ejemplos)")
    ap.add_argument("--semilla", type=int, default=2026)
    a = ap.parse_args()
    destino = a.salida or EJEMPLOS
    destino.mkdir(parents=True, exist_ok=True)
    esperados = {}
    if a.lote:
        rng = random.Random(a.semilla)
        for i in range(a.lote):
            clave, captura = ["mamaria", "citologia"][i % 2], ["foto", "escaneo"][(i // 2) % 2]
            nombre = f"lote_{i:03d}_{clave}_{captura}." + ("png" if captura == "foto" else "pdf")
            valores = persona(rng, f"AT-{rng.randint(100, 999)}", clave == "citologia")
            documento(destino / nombre, clave, captura, valores, rng)
            esperados[nombre] = {"formato": clave, "valores": valores}
    else:
        for viejo in ("ejemplo_formulario.pdf", "ejemplo_formulario.png", "ejemplo_escaneado.pdf", "formato_en_blanco.pdf"):
            (destino / viejo).unlink(missing_ok=True)
        for i, (nombre, clave, captura, folio, letra) in enumerate(EJEMPLOS_FIJOS):
            rng = random.Random(a.semilla + i)
            valores = persona(rng, folio, clave == "citologia")
            documento(destino / nombre, clave, captura, valores, rng, letra)
            esperados[nombre] = {"formato": clave, "valores": valores}
        blanco = llenar("mamaria", {}, Mano(random.Random(1)))
        a_pdf([escaneo(hj, random.Random(7 + i)) for i, hj in enumerate(blanco)], destino / "formato_en_blanco_escaneo.pdf", 110)
        excel(destino / "ejemplo_atenciones_nuevas.xlsx")
    (destino / "valores_esperados.json").write_text(json.dumps(esperados, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in sorted(destino.iterdir()):
        print(p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
