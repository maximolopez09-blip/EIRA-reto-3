import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eira import db  # noqa: E402
from eira.tabular import registros_automaticos  # noqa: E402


def cargar(conn, path: Path, nombre: str | None = None, contenido: bytes | None = None):
    contenido = contenido if contenido is not None else path.read_bytes()
    nombre = nombre or path.name
    regs = registros_automaticos(nombre, contenido)
    tipo = "csv" if nombre.lower().endswith(".csv") else "excel"
    return db.confirmar(conn, regs, [], nombre, hashlib.sha256(contenido).hexdigest(), tipo)


@pytest.fixture
def conn(tmp_path):
    c = db.conectar(tmp_path / "prueba.db")
    yield c
    c.close()
