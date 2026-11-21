import hashlib

import pandas as pd
import pytest

from conftest import cargar
from eira import db, documents, report
from eira.config import CITA, EJEMPLOS, ROOT

HAY_OCR = documents.tesseract_cmd() is not None
FORMATOS = ROOT.parent / "Formatos"


def procesar(nombre):
    return documents.procesar(nombre, (EJEMPLOS / nombre).read_bytes())


def guardar(conn, doc, nombre):
    r = documents.a_registro(doc, nombre)
    return db.confirmar(conn, [r], [], nombre, hashlib.sha256(nombre.encode()).hexdigest(), "pdf"), r


def test_pdf_con_texto(conn):
    doc = procesar("ejemplo_formulario.pdf")
    assert doc["metodo"] == "texto PDF" and not doc["sin_datos"] and doc["error"] is None
    c = doc["campos"]
    assert (c["folio"], c["fecha"], c["nombre"], c["edad"], c["municipio"]) == ("AT-201", "05/10/2026", "Rosa Elena Martínez Gil", 52, "Sayula")
    assert c["padecimiento"] == "BIRADS 2 - Hallazgos benignos"
    assert (c["programa"], c["servicio"]) == ("Detección oportuna", "Revisión mamaria")
    res, r = guardar(conn, doc, "ejemplo_formulario.pdf")
    assert res["nuevos"] == 1 and r["ubicacion"] == "página 1"
    f, _ = report.filtrar(db.actividades_df(conn), municipios=["Sayula"])
    assert "AT-201" in set(f["folio"])


@pytest.mark.skipif(not HAY_OCR, reason="Tesseract no instalado")
@pytest.mark.parametrize("nombre,metodo", [("ejemplo_formulario.png", "OCR"), ("ejemplo_escaneado.pdf", "OCR (PDF escaneado)")])
def test_ocr_png_y_pdf_escaneado(conn, nombre, metodo):
    doc = procesar(nombre)
    assert doc["metodo"] == metodo and doc["error"] is None
    c = doc["campos"]
    assert (c["folio"], c["fecha"], c["nombre"], c["edad"], c["municipio"]) == ("AT-202", "12/10/2026", "Carmen Díaz Ochoa", 47, "Tuxpan")
    assert c["padecimiento"] is None  # el formato no registra diagnóstico: «No registrado»
    assert guardar(conn, doc, nombre)[0]["nuevos"] == 1


def test_formato_en_blanco_sin_datos():
    doc = procesar("formato_en_blanco.pdf")
    assert doc["sin_datos"] and doc["campos"]["folio"] is None and doc["campos"]["nombre"] is None
    assert doc["campos"]["padecimiento"] is None


@pytest.mark.skipif(not FORMATOS.exists(), reason="Formatos de EIRA no disponibles")
def test_formatos_reales_en_blanco():
    for p in FORMATOS.glob("Formato*"):
        if p.suffix.lower() == ".pdf" or HAY_OCR:
            doc = documents.procesar(p.name, p.read_bytes())
            assert doc["sin_datos"], p.name
            assert doc["campos"]["padecimiento"] is None, p.name


def test_falla_ocr_permite_captura_manual(monkeypatch):
    monkeypatch.setenv("TESSERACT_CMD", r"C:\no\existe\tesseract.exe")
    doc = procesar("ejemplo_formulario.png")
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
