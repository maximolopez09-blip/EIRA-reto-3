"""Plantillas de los formatos de EIRA: dónde está cada etiqueta impresa y cada espacio a llenar (en puntos)."""
import json
from pathlib import Path

PLANTILLAS = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(__file__).parent / "formatos").glob("*.json"))}
