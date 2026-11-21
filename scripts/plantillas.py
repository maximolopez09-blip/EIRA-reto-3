"""Construye los formatos en blanco y sus plantillas de campos (posición de cada etiqueta impresa y de cada espacio a llenar).

- Formato de revisión mamaria (2 páginas): se redibuja aquí a partir de las fotos del formato real.
- Solicitud y reporte de citología cervical (1 página): se usa el PDF original de EIRA.

Uso: python scripts/plantillas.py   ->  Datos/formatos/*.pdf  y  eira/formatos/*.json
"""
import json
import sys
from pathlib import Path

import pypdfium2 as pdfium
from fpdf import FPDF

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eira.config import DATOS, ROOT  # noqa: E402
from eira.pdftexto import es_raya, palabras_pdf  # noqa: E402

AQUI = Path(__file__).resolve().parent
FUENTES = AQUI / "fuentes"
FORMATOS = DATOS / "formatos"
PLANTILLAS = ROOT / "eira" / "formatos"
SI_NO = {"1": "Sí", "2": "No"}
GRIS = 128


class Hoja:
    """Dibuja con fpdf2 y anota la caja (en puntos) de cada espacio a llenar."""

    def __init__(self):
        self.p = FPDF(unit="pt", format=(612, 792))
        self.p.set_auto_page_break(False)
        self.p.add_font("Carlito", "", str(FUENTES / "Carlito-Regular.ttf"))
        self.p.add_font("Carlito", "B", str(FUENTES / "Carlito-Bold.ttf"))
        self.p.set_line_width(0.6)
        self.campos = []

    def pagina(self):
        self.p.add_page()

    def t(self, x, y, s, b=False, sz=8.5, color=0, centro=False):
        self.p.set_font("Carlito", "B" if b else "", sz)
        self.p.set_text_color(color)
        w = self.p.get_string_width(s)
        if centro:
            x -= w / 2
        self.p.text(x, y, s)
        return x + w

    def raya(self, nombre, x0, x1, y, tipo="texto", **extra):
        self.p.set_draw_color(0)
        self.p.set_line_width(0.5)
        self.p.line(x0, y + 1.5, x1, y + 1.5)
        self._campo(nombre, [x0, y - 14, x1, y + 3], tipo, **extra)
        return x1

    def caja(self, nombre, x, y, opciones=None, w=22, h=11.5, tipo="codigo", **extra):
        self.marco(x, y - 9, x + w, y - 9 + h)
        self._campo(nombre, [x, y - 9, x + w, y - 9 + h], tipo, opciones=opciones, **extra)
        return x + w

    def marco(self, x0, y0, x1, y1, relleno=None, ancho=0.6):
        self.p.set_draw_color(0)
        self.p.set_line_width(ancho)
        if relleno is not None:
            self.p.set_fill_color(relleno)
        self.p.rect(x0, y0, x1 - x0, y1 - y0, style="DF" if relleno is not None else "D")

    def banda(self, x0, y0, x1, y1, titulo):
        self.marco(x0, y0, x1, y1, relleno=GRIS)
        self.t((x0 + x1) / 2, y1 - 3, titulo, sz=8.5, color=255, centro=True)

    def _campo(self, nombre, caja, tipo, **extra):
        c = {"nombre": nombre, "pagina": self.p.page_no() - 1, "caja": [round(v, 1) for v in caja], "tipo": tipo}
        c.update({k: v for k, v in extra.items() if v is not None})
        self.campos.append(c)


def logo_gris() -> Path:
    """El logotipo sale del PDF de citología (rosa) y se pasa a gris, como en el formato mamario."""
    ruta = AQUI / "recursos" / "logo_eira_gris.png"
    if not ruta.exists():
        pag = pdfium.PdfDocument(str(FORMATOS / "citologia_cervical.pdf"))[0]
        img = max((o.get_bitmap(render=True).to_pil() for o in pag.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE])),
                  key=lambda i: i.width)
        la = img.convert("LA")
        la.putdata([(120, a) for _, a in la.getdata()])
        ruta.parent.mkdir(exist_ok=True)
        la.save(ruta)
    return ruta


def mamaria() -> tuple[FPDF, list[dict]]:
    h = Hoja()
    t, raya, caja = h.t, h.raya, h.caja
    X0, X1 = 59, 553

    # ---------- Página 1 ----------
    h.pagina()
    t(70, 37, "Folio Eira", b=True)
    h.marco(69, 51, 185, 67)
    h.p.line(128, 51, 128, 67)
    h._campo("folio", [69, 51, 185, 67], "folio")
    h.p.image(str(logo_gris()), 255, 50, 132)
    x = t(449, 64, "Talla:")
    x = raya("talla", x, x + 28, 64, "numero")
    x = t(x, 64, "Peso:")
    raya("peso", x, x + 28, 64, "numero")
    x = t(449, 85, "PA:")
    x = raya("presion_arterial", x + 8, x + 44, 85, "numero")
    x = t(x, 85, "GLC:")
    raya("glucosa", x + 2, x + 28, 85, "numero")
    x = t(449, 106, "BT:")
    x = raya("bt", x + 8, x + 38, 106, "numero")
    x = t(x + 10, 106, "AT:")
    raya("at", x, x + 28, 106, "numero")
    t(73, 93, "Cuenta de cartilla Eira", b=True)
    caja("cartilla", 70, 113, SI_NO)
    t(120, 115, "1.  Si   2. No")
    t(306, 151, "PREVENCION Y DETECCIÓN OPORTUNA DE CÁNCER DE MAMA", b=True, sz=9, centro=True)
    t(306, 168, "FORMATO DE REVISIÓN MAMARIA", b=True, sz=9, centro=True)

    h.marco(X0, 204, X1, 441)
    h.marco(299, 193, 389, 211, relleno=GRIS)
    t(303, 205, "1.Fecha de atención", b=True, color=255)
    for nombre, etq, a, b in [("atencion_dia", "Día", 389, 432), ("atencion_mes", "Mes", 432, 498), ("atencion_anio", "Año", 498, X1)]:
        h.marco(a, 193, b, 211, relleno=255)
        e = t(a + 4, 205, etq)
        h._campo(nombre, [e + 2, 194, b - 1, 210], "numero")
    h.banda(X0, 211, X1, 224, "Datos de identificación")
    x = t(64, 238, "2.Nombre")
    raya("nombre", x, 532, 238)
    x = t(64, 259, "3. Entidad de nacimiento")
    raya("entidad_nacimiento", x, 362, 259)
    t(366, 276, "4.ID")
    for i in range(11):
        h.marco(393 + i * 12.2, 268, 393 + (i + 1) * 12.2, 283)
    h._campo("id", [393, 268, 393 + 11 * 12.2, 283], "casillas", n=11)
    x = t(64, 289, "5. Fecha de nacimiento Día")
    x = raya("nacimiento_dia", x, x + 30, 289, "numero")
    x = t(x, 289, "Mes")
    x = raya("nacimiento_mes", x, x + 30, 289, "numero")
    x = t(x, 289, "Año")
    x = raya("nacimiento_anio", x, x + 30, 289, "numero")
    x = t(x, 289, "6. Edad en años")
    raya("edad", x + 2, x + 38, 289, "numero")
    t(72, 301, "7. Residencia habitual")
    raya("residencia#1", 66, 524, 318)
    raya("residencia#2", 66, 524, 334)
    x = t(64, 347, "8. Teléfono fijo")
    x = raya("telefono_fijo", x, x + 118, 347, "numero")
    x = t(x, 347, "Celular")
    raya("celular", x, x + 118, 347, "numero")
    x = t(64, 367, "9. Afiliación")
    x = caja("afiliacion", x + 6, 367, {"1": "INSABI", "2": "IMSS", "3": "ISSSTE", "4": "SEDENA", "5": "SEMAR", "6": "Ninguno", "7": "Otro"})
    x = t(x + 12, 367, "1. INSABI 2. IMSS 3. ISSSTE 4. SEDENA 5. SEMAR 6. Ninguno 7. Otro")
    raya("afiliacion_otro", x, 528, 367)
    t(64, 387, "10. Motivo de consulta")
    for i, y in enumerate((402, 417, 430)):
        raya(f"motivo_consulta#{i + 1}", 66, 532, y)

    h.marco(X0, 455, X1, 678)
    h.banda(X0, 455, X1, 466, "Factores de riesgo")
    x = t(61, 476, "11. Edad de presentación de la menarca")
    x = caja("menarca", x + 6, 476, tipo="numero")
    t(x + 10, 477, "años")
    x = t(61, 502, "12. Familiares con antecedente de cáncer mamario")
    x = caja("familiares_cancer_mamario", x + 4, 502,
             {"1": "Madre", "2": "Hermana", "3": "Hija", "4": "Madre y hermana", "5": "Madre e hija", "6": "Hermana e hija", "7": "Ninguno"})
    t(x + 8, 502, "1. Madre 2. Hermana 3. Hija 4. 1-2 5. 1-3 6. 2-3 7. Ninguno")
    x = t(61, 523, "13. FUM Día")
    x = raya("fum_dia", x, x + 28, 523, "numero")
    x = t(x, 523, "Mes")
    x = raya("fum_mes", x, x + 28, 523, "numero")
    x = t(x, 523, "Año")
    raya("fum_anio", x, x + 24, 523, "numero")
    x = t(61, 548, "14.Anticoncepción. Tipo")
    x = raya("anticoncepcion_tipo", x, x + 84, 548)
    x = t(x, 548, "Inicio")
    x = raya("anticoncepcion_inicio", x, x + 80, 548)
    x = t(x, 548, "Tiempo")
    x = raya("anticoncepcion_tiempo", x, x + 76, 548)
    x = t(x, 548, "Suspensión")
    raya("anticoncepcion_suspension", x, 546, 548)
    x = t(61, 572, "15.Edad de presentación de la menopausia")
    x = caja("menopausia", x + 4, 572, tipo="numero")
    t(x + 6, 573, "años")
    x = t(61, 598, "16.Antecedente de mastografía")
    x = caja("antecedente_mastografia", x + 4, 598, SI_NO)
    x = t(x + 6, 598, "1. Si 2. No 16.1 Fecha de última mastografía Día")
    x = raya("ultima_mastografia_dia", x, x + 24, 598, "numero")
    x = t(x, 598, "Mes")
    x = raya("ultima_mastografia_mes", x, x + 24, 598, "numero")
    x = t(x, 598, "Año")
    raya("ultima_mastografia_anio", x, x + 24, 598, "numero")
    x = t(61, 611, "16.2 Resultados última mastografía")
    x = raya("resultado_ultima_mastografia", x, x + 158, 611)
    x = t(x, 611, "Observaciones")
    raya("observaciones_mastografia", x, 546, 611)
    x = t(61, 637, "17. Otros factores de riesgo")
    raya("otros_factores_riesgo#1", x + 2, 546, 637)
    raya("otros_factores_riesgo#2", 61, 546, 652)
    raya("otros_factores_riesgo#3", 61, 546, 666)

    # ---------- Página 2 ----------
    h.pagina()
    h.marco(X0, 59, X1, 438)
    h.banda(X0, 59, X1, 71, "Evaluación diagnóstica")
    t(63, 86, "18. Resultados a la exploración clínica")
    for i, y in enumerate((101, 115, 129, 143)):
        raya(f"exploracion_clinica#{i + 1}", 87, 536, y)
    x = t(63, 169, "19. Resultados a la termografía")
    x = caja("termografia", x + 6, 169, {"1": "Simétrico", "2": "Asimétrico"})
    t(x + 10, 169, "1. Simétrico 2. Asimétrico")
    t(63, 192, "20. Resultados al ultrasonido")
    h.marco(82, 199, 532, 408)
    t(88, 212, "Ultrasonido mamario realizado con ultrasonido 5 de CHISON con transductor de 10MHZ.")
    for i in range(12):
        raya(f"ultrasonido#{i + 1}", 88, 526, 236 + i * 14.6)
    x = t(63, 424, "21. Nombre, firma y cédula profesional de quien realizó estudio")
    raya("responsable_estudio", x + 2, 536, 424)

    h.marco(X0, 460, X1, 518)
    h.banda(X0, 460, X1, 472, "Diagnóstico")
    x = t(63, 483, "22. BIRADS")
    x = caja("birads", x + 4, 483, {"0": "Estudio no concluyente", "1": "Mama normal", "2": "Hallazgos benignos",
                                    "3": "Hallazgos probablemente benignos", "4": "Probablemente maligno", "5": "Hallazgos malignos"})
    t(x + 6, 483, "0. Estudio no concluyente 1. Mama normal 2. Hallazgos benignos 3. Hallazgos probablemente benignos")
    t(63, 497, "4. Probablemente maligno 5. Hallazgos malignos")

    h.marco(X0, 541, X1, 617)
    h.banda(X0, 541, X1, 553, "Referencia")
    x = t(63, 565, "23. Conducta a seguir")
    x = caja("conducta_a_seguir", x + 5, 565, {"1": "Detección de rutina en un año", "2": "Mastografía de tamizaje",
                                               "3": "Referencia a evaluación con imagen complementaria", "4": "Evaluación en seis meses"})
    t(x + 8, 565, "1. Detección de rutina en un año 2. Mastografía de tamizaje 3. Referencia a evaluación con")
    t(63, 579, "imagen complementaria 4. Evaluación en seis meses")
    x = t(63, 606, "24.Motivo de referencia")
    x = caja("motivo_referencia", x + 5, 606, {"1": "Tumoración palpable", "2": "Signos sugestivos", "3": "Estudio anormal", "4": "Factores de riesgo"})
    t(x + 6, 606, "1. Tumoración palpable 2. Signos sugestivos 3. Estudio anormal 4. Factores de riesgo.")
    t(101, 627, "Notas:", b=True)
    for i, y in enumerate((646, 662, 678)):
        raya(f"notas#{i + 1}", 98, 500, y)
    t(36, 706, "Contacto", b=True)
    t(36, 719, "Plaza Anita Ciudad Guzmán Jalisco, Federico del Toro No. 83 Int 205")
    t(36, 732, "Cel. 3411596782  Tel fijo. 3414108111  Facebook: Eira, Movimiento Rosa A.C.")
    t(36, 746, "www.eiraac.org     Email: hola@eiraac.org")
    t(432, 754, "Sello institucional", sz=9)
    return h.p, h.campos


# ---------- Citología: las rayas («____») del PDF original, en orden de lectura, y sus casillas ----------
RAYAS_CITOLOGIA = [
    ("nombre", "texto"), ("entidad_nacimiento", "texto"), ("nacimiento_dia", "numero"), ("nacimiento_mes", "numero"),
    ("nacimiento_anio", "numero"), ("edad", "numero"), ("residencia#1", "texto"), ("residencia#2", "texto"), ("telefono", "numero"),
    ("otro_domicilio", "texto"), ("otro_telefono", "numero"), ("correo", "texto"), ("numero_afiliacion", "numero"),
    ("inicio_vida_sexual_edad", "numero"), ("vacunacion_vph_edad", "numero"), ("ultima_regla_dia", "numero"),
    ("ultima_regla_mes", "numero"), ("ultima_regla_anio", "numero"), ("utensilio_otro", "texto"), ("cedula_toma", "numero"),
    ("toma_dia", "numero"), ("toma_mes", "numero"), ("toma_anio", "numero"), ("numero_citologico_anterior", "texto"),
    ("interpretacion_dia", "numero"), ("interpretacion_mes", "numero"), ("interpretacion_anio", "numero"),
    ("numero_citologico", "texto"), ("laboratorio", "texto"), ("motivo_repetir_otro", "texto"), ("cedula_citotecnologo", "numero"),
    ("diagnostico_patologo", "texto"), ("diagnostico_patologo_otros", "texto"), ("cedula_patologo", "numero"),
]
BETHESDA = {"1": "Negativa para lesión intraepitelial o malignidad", "2": "ASC-US", "3": "ASC-H",
            "4": "Lesión escamosa intraepitelial de bajo grado", "5": "Lesión escamosa intraepitelial de alto grado",
            "6": "Carcinoma epidermoide", "7": "Células glandulares endocervicales atípicas (AGC)",
            "8": "Células glandulares endometriales atípicas (AGC)", "9": "Células glandulares atípicas (AGC)",
            "10": "Adenocarcinoma endocervical in situ", "11": "Adenocarcinoma"}
OTROS_HALLAZGOS = {"1": "Trichomonas vaginalis", "2": "Microorganismos micóticos compatibles con cándida sp",
                   "3": "Flora sugestiva de vaginosis bacteriana", "4": "Microorganismos compatibles con actinomices sp",
                   "5": "Cambios compatibles con virus de herpes simple", "6": "Cambios compatibles con citomegalovirus",
                   "7": "Metaplasia escamosa tubular o cambios queratolíticos", "8": "Cambios asociados al embarazo",
                   "9": "Inflamación", "10": "Atrofia", "11": "Radioterapia", "12": "Dispositivo intrauterino",
                   "13": "Células glandulares post-histerectomía", "14": "Células endometriales no atípicas en mujeres de 45 o más"}
RIESGO = {"1": "Inicio de relaciones sexuales antes de los 18 años", "2": "Múltiples parejas sexuales",
          "3": "Antecedentes de infecciones de transmisión sexual", "4": "Tabaquismo", "5": "Ninguno"}
CASILLAS_CITOLOGIA = [
    ("afiliacion", [68.8, 236.7, 85.1, 245.6], {"1": "INSABI", "2": "IMSS", "3": "ISSSTE", "4": "PEMEX", "5": "SEDENA", "6": "SEMAR", "7": "Ninguno", "8": "Otro"}),
    ("citologia", [65.1, 275.8, 81.4, 284.7], {"1": "Primera vez en la vida", "2": "Primera vez después de 3 años", "3": "Subsecuente", "4": "Complementaria a resultado positivo a VPH"}),
    ("situacion_ginecoobstetrica", [130.3, 297.2, 146.5, 306.1], {"1": "Puerperio o postaborto", "2": "Postmenopausia", "3": "Usos hormonales", "4": "DIU", "5": "Histerectomía", "6": "Tratamiento farmacológico", "7": "Embarazo actual", "8": "Tratamiento colposcópico previo", "9": "Ninguno de los anteriores"}),
    ("inicio_vida_sexual", [100.9, 329.2, 117.2, 338.0], SI_NO),
    ("vacunacion_vph", [381.5, 329.2, 397.8, 338.0], SI_NO),
    ("vph_dosis", [70.3, 351.4, 87.5, 361.1], {"1": "Una", "2": "Dos", "3": "Tres", "4": "Completo"}),
    ("exploracion", [124.6, 375.4, 141.1, 384.4], {"1": "Cuello aparentemente sano", "2": "Cuello anormal", "3": "Lesión del cuello", "4": "Cervicitis", "5": "Leucorrea", "6": "Sangrado anormal", "7": "No se observa cuello"}),
    ("utensilio", [165.6, 395.6, 181.8, 404.5], {"1": "Espátula de Ayre modificada", "2": "Citobrush", "3": "Hisopo", "4": "Otro"}),
    ("factor_riesgo_1", [94.2, 454.1, 110.5, 462.9], RIESGO),
    ("factor_riesgo_2", [114.0, 454.1, 130.3, 462.9], RIESGO),
    ("factor_riesgo_3", [133.8, 454.1, 150.1, 462.9], RIESGO),
    ("cartilla", [113.1, 486.0, 129.4, 494.9], SI_NO),
    ("muestra_repetida", [90.7, 507.5, 107.0, 516.3], SI_NO),
    ("caracteristicas_muestra", [130.4, 577.3, 146.7, 586.2], {"1": "Adecuada", "2": "Inadecuada"}),
    ("diagnostico_citologico", [107.6, 598.8, 123.9, 607.6], BETHESDA),
    ("otros_hallazgos", [359.0, 598.8, 375.3, 607.6], OTROS_HALLAZGOS),
    ("repetir_estudio", [85.9, 867.0, 102.2, 875.9], SI_NO),
    ("motivo_repetir", [184.8, 867.0, 201.1, 875.9], {"1": "Artificios, hemorragia, inflamación o necrosis", "2": "Laminilla rota", "3": "Frotis grueso", "4": "Muestra mal fijada", "5": "Otros"}),
    ("revisada_por_patologo", [179.9, 907.0, 196.2, 915.8], SI_NO),
]


def campos_citologia(palabras: list[dict]) -> list[dict]:
    rayas = sorted((w for w in palabras if es_raya(w["t"])), key=lambda w: (round(w["caja"][1] / 4), w["caja"][0]))
    assert len(rayas) == len(RAYAS_CITOLOGIA), len(rayas)
    campos = [{"nombre": "folio", "pagina": 0, "caja": [12.8, 36.0, 102.0, 71.2], "tipo": "folio"},
              {"nombre": "id", "pagina": 0, "caja": [350.0, 123.0, 483.3, 137.0], "tipo": "casillas", "n": 10}]
    for (nombre, tipo), w in zip(RAYAS_CITOLOGIA, rayas):
        x0, _, x1, y1 = w["caja"]
        campos.append({"nombre": nombre, "pagina": 0, "caja": [x0, round(y1 - 15.5, 1), x1, round(y1 + 1.5, 1)], "tipo": tipo})
    for nombre, caja, opciones in CASILLAS_CITOLOGIA:
        campos.append({"nombre": nombre, "pagina": 0, "caja": caja, "tipo": "codigo", "opciones": opciones})
    return campos


def plantilla(clave: str, titulo: str, servicio: str, ruta_pdf: Path, campos: list[dict]) -> dict:
    pdf = pdfium.PdfDocument(str(ruta_pdf))
    paginas = []
    for i in range(len(pdf)):
        pag = pdf[i]
        paginas.append({"ancho": round(pag.get_width(), 1), "alto": round(pag.get_height(), 1),
                        "palabras": [w for w in palabras_pdf(pag) if not es_raya(w["t"])],
                        "campos": [{k: v for k, v in c.items() if k != "pagina"} for c in campos if c["pagina"] == i]})
    return {"clave": clave, "titulo": titulo, "servicio": servicio, "archivo": ruta_pdf.name, "paginas": paginas}


def main():
    FORMATOS.mkdir(parents=True, exist_ok=True)
    PLANTILLAS.mkdir(parents=True, exist_ok=True)
    pdf, campos = mamaria()
    ruta = FORMATOS / "revision_mamaria.pdf"
    pdf.output(str(ruta))
    salidas = [plantilla("mamaria", "Formato de revisión mamaria", "Revisión mamaria", ruta, campos)]
    ruta = FORMATOS / "citologia_cervical.pdf"
    palabras = palabras_pdf(pdfium.PdfDocument(str(ruta))[0])
    salidas.append(plantilla("citologia", "Solicitud y reporte de citología cervical", "Toma de citología", ruta, campos_citologia(palabras)))
    for s in salidas:
        destino = PLANTILLAS / f"{s['clave']}.json"
        destino.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        print(destino.relative_to(ROOT), sum(len(p["campos"]) for p in s["paginas"]), "campos")


if __name__ == "__main__":
    main()
