"""Recorrido de la interfaz con streamlit.testing (sin navegador)."""
import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def at(tmp_path, monkeypatch):
    monkeypatch.setenv("EIRA_DB", str(tmp_path / "app.db"))
    import importlib

    import eira.config
    importlib.reload(eira.config)
    import eira.db
    importlib.reload(eira.db)
    t = AppTest.from_file(APP, default_timeout=60)
    t.run()
    assert not t.exception, t.exception
    return t


def boton(at, etiqueta):
    return next(b for b in at.button if b.label == etiqueta)


def metrica(at, etiqueta):
    return next(m.value for m in at.metric if m.label == etiqueta)


def test_recorrido_excel(at):
    boton(at, "Cargar datos de ejemplo").click().run()
    assert not at.exception, at.exception
    claves = [b.key for b in at.button if (b.key or "").startswith("aplicar_")]
    assert len(claves) == 2
    for k in claves:
        at.button(key=k).click().run()
        assert not at.exception, at.exception
    boton(at, "Confirmar y guardar").click().run()
    assert not at.exception, at.exception
    assert metrica(at, "Atenciones") == "120"
    assert metrica(at, "Participaciones") == "80"
    assert any("pendiente de validación" in w.value for w in at.warning)


def entrada_doc(at, campo):
    return next(t for t in at.text_input if (t.key or "").startswith("doc_") and t.key.endswith("_" + campo))


def test_recorrido_png_con_correccion(at):
    boton(at, "Ejemplo PNG").click().run()
    assert not at.exception, at.exception
    assert entrada_doc(at, "folio").value == "AT-202"
    entrada_doc(at, "municipio").set_value("Zapotiltic").run()
    assert any(c.value == "↳ Corregido en revisión" for c in at.caption)
    boton(at, "Confirmar y guardar").click().run()
    assert not at.exception, at.exception
    assert metrica(at, "Atenciones") == "1"
    import eira.db as edb
    conn = edb.conectar(os.environ["EIRA_DB"])
    act = edb.actividades_df(conn).set_index("folio")
    assert act.loc["AT-202", "municipio"] == "Zapotiltic" and act.loc["AT-202", "metodo"] == "OCR"
    ext = edb.extra(act.loc["AT-202", "valores_originales_json"])["extraccion"]
    assert ext["municipio"] == "Corregido en revisión" and ext["nombre"] == "Extraído automáticamente"
    bit = edb.cambios_df(conn)
    assert ((bit.folio == "AT-202") & (bit.campo == "municipio") & (bit.valor_anterior == "Tuxpan")).any()


def test_formato_en_blanco_y_captura_manual(at, monkeypatch):
    monkeypatch.setenv("TESSERACT_CMD", r"C:\no\existe\tesseract.exe")
    boton(at, "Ejemplo PNG").click().run()
    assert any("Tesseract" in e.value for e in at.error)
    assert any("Sin datos suficientes" in w.value for w in at.warning)
    entrada_doc(at, "folio").set_value("AT-250").run()
    entrada_doc(at, "nombre").set_value("Captura Manual Prueba").run()
    assert any(c.value == "↳ Captura manual" for c in at.caption)
    boton(at, "Confirmar y guardar").click().run()
    assert not at.exception, at.exception
    import eira.db as edb
    act = edb.actividades_df(edb.conectar(os.environ["EIRA_DB"])).set_index("folio")
    assert act.loc["AT-250", "metodo"] == "captura manual"
