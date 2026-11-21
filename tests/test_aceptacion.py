import io
from datetime import date
from pathlib import Path

import openpyxl
import pandas as pd
import pypdfium2 as pdfium
import pytest

from conftest import cargar
from eira import db, report
from eira.config import DATOS, ROOT, SIN_MUNICIPIO

ATEN, PART = DATOS / "atenciones.xlsx", DATOS / "participaciones.xlsx"
ORIGINAL = ROOT.parent / "Original Data" / "atenciones.xlsx"


def bases(conn):
    return cargar(conn, ATEN), cargar(conn, PART)


def conteos(conn, **filtros):
    f, excl = report.filtrar(db.actividades_df(conn), **filtros)
    return report.resumen(f, db.mapa_personas(conn), db.identidades_pendientes(conn)), excl


def sugerencia(conn, a, b):
    s = db.sugerencias_df(conn)
    fila = s[(s.folio_a == a) & (s.folio_b == b)]
    return None if fila.empty else fila.iloc[0]


def test_totales_sin_filtros(conn):
    ra, rp = bases(conn)
    assert ra["nuevos"] == 120 and rp["nuevos"] == 80
    res, _ = conteos(conn)
    assert (res["atenciones"], res["participaciones"]) == (120, 80)


def test_sayula(conn):
    bases(conn)
    res, _ = conteos(conn, municipios=["Sayula"])
    assert (res["atenciones"], res["participaciones"]) == (25, 19)


def test_pa041_sin_municipio_y_pa042_fecha_invalida(conn):
    bases(conn)
    res, _ = conteos(conn, municipios=[SIN_MUNICIPIO])
    assert res["participaciones"] == 1
    act = db.actividades_df(conn).set_index("folio")
    assert pd.isna(act.loc["PA-041", "municipio"])
    assert act.loc["PA-042", "fecha_valida"] == 0 and act.loc["PA-042", "fecha_original"] == "31/09/2026"
    # Cuenta en el total general y se excluye del filtro por fecha.
    res_rango, excluidas = conteos(conn, rango=(date(2026, 1, 1), date(2026, 12, 31)))
    assert res_rango["participaciones"] == 79 and excluidas == 1


def test_homonimas_separadas_por_defecto(conn):
    bases(conn)
    s = sugerencia(conn, "AT-001", "AT-002")
    assert s is not None and s["estado"] == db.PENDIENTE
    assert "edad distinta" in s["motivo"] and "municipio distinto" in s["motivo"]
    personas = db.mapa_personas(conn)
    assert personas["AT-001"] != personas["AT-002"]


def test_errata_sugiere_revision_y_conserva_eventos(conn):
    bases(conn)
    s = sugerencia(conn, "AT-003", "PA-003")
    assert s is not None and s["estado"] == db.PENDIENTE and "Escritura similar" in s["motivo"]
    folios = set(db.actividades_df(conn)["folio"])
    assert {"AT-003", "PA-003"} <= folios


def test_mayusculas_y_espacios(conn):
    bases(conn)
    assert sugerencia(conn, "AT-006", "PA-006") is not None
    assert sugerencia(conn, "AT-008", "PA-008") is not None


def test_recarga_conserva_totales(conn):
    bases(conn)
    ra, rp = bases(conn)
    assert ra == {"nuevos": 0, "sin_cambios": 120, "conflictos": 0, "omitidos": 0}
    assert rp["nuevos"] == 0 and rp["conflictos"] == 0
    res, _ = conteos(conn)
    assert (res["atenciones"], res["participaciones"]) == (120, 80)


def test_csv_con_nombre_completo(conn, tmp_path):
    frame = pd.read_excel(PART, dtype=object)
    frame["dia_evento"] = frame["dia_evento"].map(lambda v: v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else v)
    contenido = frame.to_csv(index=False).encode("utf-8-sig")
    cargar(conn, ATEN)
    r = cargar(conn, Path("participaciones.csv"), "participaciones.csv", contenido)
    assert r["nuevos"] == 80
    res, _ = conteos(conn, municipios=["Sayula"])
    assert (res["atenciones"], res["participaciones"]) == (25, 19)
    # Recargar el xlsx con los mismos datos no cambia nada.
    assert cargar(conn, PART)["nuevos"] == 0 and cargar(conn, PART)["conflictos"] == 0


def test_beneficiarias_pendientes_y_vinculo_humano(conn):
    bases(conn)
    res, _ = conteos(conn)
    assert res["unicas"] is None and res["pendientes"] > 0
    db.guardar_decisiones(conn, [("AT-003", "PA-003", db.VINCULAR)])
    personas = db.mapa_personas(conn)
    assert personas["AT-003"] == personas["PA-003"]
    assert personas["AT-001"] != personas["AT-002"]
    bit = db.cambios_df(conn)
    assert (bit["campo"] == "identidad").sum() == 1


def test_decisiones_sobreviven_recarga(conn):
    bases(conn)
    db.guardar_decisiones(conn, [("AT-001", "AT-002", db.DISTINTAS)])
    bases(conn)
    assert sugerencia(conn, "AT-001", "AT-002")["estado"] == db.DISTINTAS


@pytest.mark.skipif(not ORIGINAL.exists(), reason="Original Data no disponible")
def test_original_folios_repetidos(conn):
    r = cargar(conn, ORIGINAL)
    assert r["nuevos"] == 120 and r["conflictos"] == 8
    assert cargar(conn, ORIGINAL)["conflictos"] == 0  # recarga idempotente
    conf = db.conflictos_df(conn)
    assert "AT-108" not in set(conf["folio"]) and "AT-111" in set(conf["folio"])
    cid = int(conf[conf.folio == "AT-111"].iloc[0]["id"])
    db.resolver_conflicto(conn, cid, aplicar=False)
    assert len(db.conflictos_df(conn)) == 7


def test_informes_sin_nombres(conn):
    bases(conn)
    filtros = {"municipios": ["Sayula"], "programas": None, "rango": None}
    f, excl = report.filtrar(db.actividades_df(conn), **filtros)
    res = report.resumen(f, db.mapa_personas(conn), db.identidades_pendientes(conn))
    ctx = report.contexto(conn, filtros, res, excl)
    nombres = set(db.actividades_df(conn)["nombre"].dropna())
    wb = openpyxl.load_workbook(io.BytesIO(report.excel_bytes(ctx)))
    textos = " ".join(str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None)
    assert "Sayula" in textos and "Fecha de corte" in textos and "PA-042" in textos
    assert not any(n in textos for n in nombres)
    pdf = pdfium.PdfDocument(report.pdf_bytes(ctx))
    texto_pdf = " ".join(p.get_textpage().get_text_range() for p in pdf)
    assert "Fecha de corte" in texto_pdf and "Atenciones" in texto_pdf
    assert not any(n in texto_pdf for n in nombres)
