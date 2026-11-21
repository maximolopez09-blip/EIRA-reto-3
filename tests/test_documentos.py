import hashlib
import io

import pandas as pd
import pytest

from conftest import cargar
from eira import db, documents, manuscrito, report
from eira.config import CITA, EJEMPLOS, ROOT
from eira.formularios import PLANTILLAS

HAY_OCR = documents.tesseract_cmd() is not None
FORMATOS = ROOT.parent / "Formatos"
HAY_LECTOR = pytest.mark.skipif(manuscrito.motor() is None, reason="RapidOCR no instalado")


def procesar(nombre):
    return documents.procesar(nombre, (EJEMPLOS / nombre).read_bytes())


def guardar(conn, doc, nombre):
    r = documents.a_registro(doc, nombre)
    return db.confirmar(conn, [r], [], nombre, hashlib.sha256(nombre.encode()).hexdigest(), "pdf"), r


def procesar_varios(*nombres):
    return documents.procesar_varios([(n, (EJEMPLOS / n).read_bytes()) for n in nombres])


def hoja_impresa(lineas):
    """Imagen de un documento impreso cualquiera (no es uno de los formatos de EIRA)."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (1400, 900), "white")
    d = ImageDraw.Draw(im)
    fuente = ImageFont.truetype(str(ROOT / "scripts" / "fuentes" / "Carlito-Regular.ttf"), 40)
    for i, t in enumerate(lineas):
        d.text((80, 80 + 80 * i), t, fill="black", font=fuente)
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def test_pdf_con_texto(conn):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    for t in ["Folio: AT-260", "Fecha: 05/10/2026", "Nombre: Rosa Elena Martinez Gil", "Edad: 52", "Municipio: Sayula"]:
        pdf.cell(0, 10, t, new_x="LMARGIN", new_y="NEXT")
    doc = documents.procesar("capturado.pdf", bytes(pdf.output()))
    assert doc["metodo"] == "texto PDF" and not doc["sin_datos"] and doc["error"] is None and doc["formulario"] is None
    c = doc["campos"]
    assert c["folio"] == "AT-260"
    res, r = guardar(conn, doc, "capturado.pdf")
    assert res["nuevos"] == 1 and r["ubicacion"] == "página 1"


@pytest.mark.skipif(not HAY_OCR, reason="Tesseract no instalado")
def test_ocr_de_documento_que_no_es_un_formato():
    doc = documents.procesar("otro.png", hoja_impresa(["Folio: AT-261", "Nombre: Carmen Ochoa", "Edad: 47"]))
    assert doc["metodo"] == "OCR" and doc["formulario"] is None and doc["error"] is None
    assert doc["campos"]["folio"] == "AT-261"


@HAY_LECTOR
def test_foto_de_dos_paginas_llenadas_a_mano(conn):
    doc = procesar_varios("mamaria_foto.png", "mamaria_foto_pagina2.png")
    f = doc["formulario"]
    assert doc["error"] is None and doc["metodo"] == "Formato llenado a mano (foto)" and len(doc["imagenes"]) == 2
    assert (f["formato"], f["paginas"]) == ("mamaria", [0, 1])
    c = doc["campos"]
    assert (c["folio"], c["edad"], c["servicio"]) == ("AT-201", 32, "Revisión mamaria")
    assert c["municipio"] == "Zapotlán el Grande"
    assert c["padecimiento"] == "BIRADS 2 - Hallazgos benignos"  # viene de la casilla BIRADS de la página 2
    res, r = guardar(conn, doc, "mamaria_foto.png")
    assert res["nuevos"] == 1 and r["originales"]["formulario"]["folio"] == "AT-201"


@HAY_LECTOR
def test_la_pagina_2_sola_no_basta():
    doc = procesar_varios("mamaria_foto_pagina2.png")
    assert doc["formulario"]["paginas"] == [1] and doc["sin_datos"]


@HAY_LECTOR
@pytest.mark.parametrize("nombre,formato,folio,edad", [("mamaria_escaneo.pdf", "mamaria", "AT-202", 31), ("citologia_escaneo.pdf", "citologia", "AT-204", 71)])
def test_escaneo_de_baja_resolucion(nombre, formato, folio, edad):
    doc = procesar_varios(nombre)
    assert doc["metodo"] == "Formato llenado a mano (PDF escaneado)" and doc["formulario"]["formato"] == formato
    assert (doc["campos"]["folio"], doc["campos"]["edad"]) == (folio, edad)


@HAY_LECTOR
def test_foto_dificil_reconoce_el_formato_y_avisa_de_lo_dudoso():
    doc = procesar_varios("citologia_foto.png")
    f = doc["formulario"]
    assert f["formato"] == "citologia" and doc["campos"]["folio"] == "AT-203"
    assert "nombre" in f["dudosos"]
    notas = documents.a_registro(doc, "citologia_foto.png")["notas"]
    assert any("Lectura dudosa de nombre" in n for n in notas)


@HAY_LECTOR
def test_sin_tesseract_el_formato_se_lee_igual(monkeypatch):
    monkeypatch.setenv("TESSERACT_CMD", r"C:\no\existe\tesseract.exe")
    doc = procesar_varios("citologia_escaneo.pdf")
    assert doc["error"] is None and doc["campos"]["folio"] == "AT-204"


@HAY_LECTOR
def test_formato_en_blanco_sin_datos():
    doc = procesar_varios("formato_en_blanco_escaneo.pdf")
    assert doc["formulario"]["formato"] == "mamaria" and not doc["formulario"]["valores"]
    assert doc["sin_datos"] and doc["campos"]["folio"] is None and doc["campos"]["nombre"] is None
    assert doc["campos"]["padecimiento"] is None


@pytest.mark.parametrize("campo,leido,esperado", [
    ({"tipo": "numero", "nombre": "edad"}, "4 7", "47"),
    ({"tipo": "codigo", "nombre": "x", "opciones": {"1": "Sí", "2": "No"}}, "2.", "2"),
    ({"tipo": "folio", "nombre": "folio"}, "AT 2O1", "AT-201"),
])
def test_interpretar(campo, leido, esperado):
    assert manuscrito.interpretar(campo, leido, 0.9)[0] == esperado


def test_plantillas_coherentes():
    for clave, pl in PLANTILLAS.items():
        nombres = [c["nombre"] for p in pl["paginas"] for c in p["campos"]]
        assert len(nombres) == len(set(nombres)), clave
        assert {"folio", "nombre", "edad"} <= set(nombres), clave
        for p in pl["paginas"]:
            for c in p["campos"]:
                x0, y0, x1, y1 = c["caja"]
                assert 0 <= x0 < x1 <= p["ancho"] and 0 <= y0 < y1 <= p["alto"], (clave, c["nombre"])


@pytest.mark.skipif(not FORMATOS.exists(), reason="Formatos de EIRA no disponibles")
def test_formatos_reales_en_blanco():
    for p in FORMATOS.glob("Formato*"):
        if p.suffix.lower() == ".pdf" or HAY_OCR:
            doc = documents.procesar(p.name, p.read_bytes())
            assert doc["sin_datos"], p.name
            assert doc["campos"]["padecimiento"] is None, p.name


def test_falla_ocr_permite_captura_manual(monkeypatch):
    monkeypatch.setenv("TESSERACT_CMD", r"C:\no\existe\tesseract.exe")
    doc = documents.procesar("otro.png", hoja_impresa(["Folio: AT-261", "Nombre: Carmen Ochoa"]))
    assert doc["error"] and "Tesseract" in doc["error"]
    assert doc["metodo"] == "captura manual" and doc["sin_datos"]
    assert doc["imagen"] is not None


def test_excel_ejemplo_columnas_distintas_y_cita(conn):
    cargar(conn, ROOT / "Datos" / "atenciones.xlsx")
    res = cargar(conn, EJEMPLOS / "ejemplo_atenciones_nuevas.xlsx")
    assert res["nuevos"] == 6
    act = db.actividades_df(conn).set_index("folio")
    assert act.loc["AT-305", "tipo_evento"] == CITA
    assert act.loc["AT-302", "padecimiento"] == "Cervicitis"
    assert pd.isna(act.loc["AT-301", "padecimiento"])
    f, _ = report.filtrar(db.actividades_df(conn))
    r = report.resumen(f, db.mapa_personas(conn), 0)
    assert (r["atenciones"], r["citas"]) == (125, 1)
    s = db.sugerencias_df(conn)
    assert len(s[(s.folio_b == "AT-303") & (s.folio_a == "AT-004")]) == 1
    assert any("AT-304" in a for a in report.advertencias(conn, db.actividades_df(conn)))
