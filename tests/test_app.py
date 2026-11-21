"""Recorrido de la interfaz con streamlit.testing (sin navegador)."""
import importlib
import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def at(tmp_path, monkeypatch):
    monkeypatch.setenv("EIRA_DB", str(tmp_path / "app.db"))
    import eira.config
    importlib.reload(eira.config)
    import eira.db
    importlib.reload(eira.db)
    t = AppTest.from_file(APP, default_timeout=90)
    t.run()
    assert not t.exception, t.exception
    return t


def bd():
    import eira.db as edb
    return edb.conectar(os.environ["EIRA_DB"])


def clic(at, key):
    at.button(key=key).click().run()
    assert not at.exception, at.exception


def metrica(at, etiqueta):
    return next(m.value for m in at.metric if m.label == etiqueta)


def entrada(at, campo):
    return next(t for t in at.text_input if (t.key or "").startswith("c_") and t.key.endswith("_" + campo))


def guardar_todo(at):
    clic(at, "sig_revisar")
    clic(at, "sig_confirmar")
    clic(at, "guardar")


def test_inicio_vacio_y_datos_de_ejemplo(at):
    assert any("Aún no hay datos" in (i.value or "") or "Empieza" in (i.value or "") for i in at.info)
    clic(at, "nav_agregar")
    clic(at, "ej_bases")
    assert any("Reconocimos atenciones.xlsx" in m.value and "120 atenciones" in m.value for m in at.markdown)
    assert any("Reconocimos participaciones.xlsx" in m.value and "80 participaciones" in m.value for m in at.markdown)
    clic(at, "sig_revisar")
    assert any("De **200** registros" in m.value for m in at.markdown)
    clic(at, "sig_confirmar")
    assert metrica(at, "Actividades nuevas") == "200"
    clic(at, "guardar")
    assert metrica(at, "Atenciones") == "120" and metrica(at, "Participaciones") == "80"
    assert metrica(at, "Beneficiarias únicas") == "Pendiente"
    at.multiselect(key="f_mun").set_value(["Sayula"]).run()
    assert metrica(at, "Atenciones") == "25" and metrica(at, "Participaciones") == "19"


def test_recarga_no_duplica(at):
    for _ in range(2):
        clic(at, "nav_agregar")
        clic(at, "ej_bases")
        guardar_todo(at)
    assert metrica(at, "Atenciones") == "120" and metrica(at, "Participaciones") == "80"


def test_fotos_de_dos_paginas_con_correccion(at):
    clic(at, "nav_agregar")
    clic(at, "ej_png")
    clic(at, "sig_revisar")
    # las fotos de las dos páginas quedan como un solo documento
    assert len([t for t in at.text_input if (t.key or "").startswith("c_") and t.key.endswith("_folio")]) == 1
    assert entrada(at, "folio").value == "AT-201"
    entrada(at, "municipio").set_value("Zapotiltic").run()
    assert any("Corregido en revisión" in c.value for c in at.caption)
    clic(at, "sig_confirmar")
    assert metrica(at, "Correcciones") == "1"
    clic(at, "guardar")
    assert metrica(at, "Atenciones") == "1"
    import eira.db as edb
    conn = bd()
    act = edb.actividades_df(conn).set_index("folio")
    assert act.loc["AT-201", "municipio"] == "Zapotiltic" and act.loc["AT-201", "metodo"] == "Formato llenado a mano (foto)"
    assert act.loc["AT-201", "padecimiento"] == "BIRADS 2 - Hallazgos benignos"
    ext = edb.extra(act.loc["AT-201", "valores_originales_json"])["extraccion"]
    assert ext["municipio"] == "Corregido en revisión" and ext["folio"] == "Extraído automáticamente"
    bit = edb.cambios_df(conn)
    assert ((bit.folio == "AT-201") & (bit.campo == "municipio") & (bit.valor_anterior == "Zapotlán el Grande")).any()


def test_formato_en_blanco_y_captura_manual(at):
    clic(at, "nav_agregar")
    clic(at, "ej_blanco")
    assert any("sin datos suficientes" in m.value for m in at.markdown)
    clic(at, "sig_revisar")
    assert any("Sin datos suficientes" in w.value for w in at.warning)
    entrada(at, "folio").set_value("AT-250").run()
    entrada(at, "nombre").set_value("Captura Manual Prueba").run()
    assert any("Captura manual" in c.value for c in at.caption)
    clic(at, "sig_confirmar")
    clic(at, "guardar")
    import eira.db as edb
    assert edb.actividades_df(bd()).set_index("folio").loc["AT-250", "nombre"] == "Captura Manual Prueba"


def test_coincidencias_una_por_una(at):
    clic(at, "nav_agregar")
    clic(at, "ej_bases")
    guardar_todo(at)
    import eira.db as edb
    antes = edb.identidades_pendientes(bd())
    clic(at, "ir_pendientes")
    assert any(s.value.startswith(f"Coincidencia 1 de {antes}") for s in at.subheader)
    clic(at, "pend_distintas")
    assert edb.identidades_pendientes(bd()) == antes - 1
    clic(at, "pend_despues")
    assert edb.identidades_pendientes(bd()) == antes - 1
    clic(at, "pend_misma")
    assert edb.identidades_pendientes(bd()) == antes - 2
    assert (edb.cambios_df(bd())["campo"] == "identidad").sum() == 2
