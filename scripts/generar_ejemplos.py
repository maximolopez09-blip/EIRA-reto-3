"""Genera los documentos y el Excel de ejemplo (todos con datos ficticios) en Datos/ejemplos/.

Uso: python scripts/generar_ejemplos.py
"""
import sys
from pathlib import Path

import pandas as pd
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eira.config import EJEMPLOS  # noqa: E402

PDF_DATOS = {"folio": "AT-201", "dia": "05", "mes": "10", "anio": "2026", "nombre": "Rosa Elena Martínez Gil", "edad": "52",
             "residencia": "Sayula", "motivo": "Revisión de rutina", "diagnostico": "BIRADS 2 - Hallazgos benignos"}
PNG_DATOS = {"folio": "AT-202", "dia": "12", "mes": "10", "anio": "2026", "nombre": "Carmen Díaz Ochoa", "edad": "47",
             "residencia": "Tuxpan", "motivo": "Molestia en mama derecha", "diagnostico": ""}

L = "__________"


def lineas(d: dict | None):
    d = d or {}
    g = lambda k, vacio=L: d.get(k) or vacio  # noqa: E731
    return [
        ("titulo", "EIRA - Movimiento Rosa A.C.   (FORMATO FICTICIO PARA PRUEBAS)"),
        ("normal", f"Folio Eira: {g('folio')}"),
        ("titulo", "PREVENCIÓN Y DETECCIÓN OPORTUNA DE CÁNCER DE MAMA"),
        ("titulo", "FORMATO DE REVISIÓN MAMARIA"),
        ("normal", f"1. Fecha de atención: Día {g('dia', '___')} Mes {g('mes', '___')} Año {g('anio', '_____')}"),
        ("seccion", "Datos de identificación"),
        ("normal", f"2. Nombre: {g('nombre', L * 3)}"),
        ("normal", "3. Entidad de nacimiento: " + ("Jalisco" if d else L)),
        ("normal", f"6. Edad en años: {g('edad', '_____')}"),
        ("normal", f"7. Residencia habitual: {g('residencia', L * 3)}"),
        ("normal", f"10. Motivo de consulta: {g('motivo', L * 3)}"),
        ("seccion", "Diagnóstico"),
        ("normal", f"22. Diagnóstico registrado: {g('diagnostico', L * 2)}"),
        ("normal", "Notas: " + ("Documento ficticio generado para la demo." if d else L * 3)),
    ]


def pdf(d, ruta: Path):
    p = FPDF(format="Letter")
    p.add_page()
    for estilo, t in lineas(d):
        p.set_font("Helvetica", "B" if estilo != "normal" else "", 13 if estilo == "titulo" else 11)
        if estilo == "seccion":
            p.set_fill_color(220, 220, 220)
        p.cell(0, 11, t, new_x="LMARGIN", new_y="NEXT", fill=estilo == "seccion", align="C" if estilo == "titulo" else "L")
    p.output(str(ruta))


def fuente(tam, negrita=False):
    for f in (["arialbd.ttf", "DejaVuSans-Bold.ttf"] if negrita else ["arial.ttf", "DejaVuSans.ttf"]):
        for base in ("C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/", ""):
            try:
                return ImageFont.truetype(base + f, tam)
            except OSError:
                continue
    return ImageFont.load_default(tam)


def png(d) -> Image.Image:
    img = Image.new("RGB", (1700, 2200), "white")
    dr = ImageDraw.Draw(img)
    y = 120
    for estilo, t in lineas(d):
        f = fuente(44 if estilo == "titulo" else 38, estilo != "normal")
        if estilo == "seccion":
            dr.rectangle([100, y - 8, 1600, y + 52], fill=(225, 225, 225))
        x = (1700 - dr.textlength(t, font=f)) / 2 if estilo == "titulo" else 120
        dr.text((x, y), t, fill="black", font=f)
        y += 115
    return img


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


def main():
    EJEMPLOS.mkdir(parents=True, exist_ok=True)
    pdf(PDF_DATOS, EJEMPLOS / "ejemplo_formulario.pdf")
    pdf(None, EJEMPLOS / "formato_en_blanco.pdf")
    img = png(PNG_DATOS)
    img.save(EJEMPLOS / "ejemplo_formulario.png")
    img.convert("L").save(EJEMPLOS / "ejemplo_escaneado.pdf", resolution=200)
    excel(EJEMPLOS / "ejemplo_atenciones_nuevas.xlsx")
    for p in sorted(EJEMPLOS.iterdir()):
        print(p.relative_to(EJEMPLOS.parent.parent), p.stat().st_size)


if __name__ == "__main__":
    main()
