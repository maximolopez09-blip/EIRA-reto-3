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
