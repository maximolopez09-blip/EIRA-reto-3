import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATOS = ROOT / "Datos"
EJEMPLOS = DATOS / "ejemplos"
DB_PATH = Path(os.environ.get("EIRA_DB", ROOT / "data" / "eira.db"))
TESSDATA = ROOT / "tessdata"

SIN_MUNICIPIO = "Sin municipio"
NO_REGISTRADO = "No registrado"
SIN_DATOS = "Sin datos suficientes"

ATENCION, PARTICIPACION, CITA = "Atención", "Participación", "Cita agendada"
TIPOS_EVENTO = [ATENCION, PARTICIPACION, CITA]

CAMPOS = ["folio", "fecha", "tipo_evento", "programa", "municipio", "nombre", "edad", "servicio", "padecimiento"]
ETIQUETAS = {
    "folio": "Folio de actividad",
    "fecha": "Fecha",
    "tipo_evento": "Tipo de evento",
    "programa": "Programa",
    "municipio": "Municipio",
    "nombre": "Nombre",
    "edad": "Edad",
    "servicio": "Servicio o actividad",
    "padecimiento": "Padecimiento (solo si la fuente lo registra)",
}

SINONIMOS = {
    "folio": ["folio", "folio_atencion", "folio_participacion", "folio_actividad", "folio eira", "id_actividad"],
    "fecha": ["fecha", "fecha_atencion", "dia_evento", "fecha_evento", "fecha de atencion", "fecha_actividad"],
    "programa": ["programa", "proyecto"],
    "municipio": ["municipio", "localidad", "municipio_residencia", "municipio de residencia", "residencia"],
    "nombre": ["nombre_completo", "nombre completo", "nombre", "paciente", "beneficiaria"],
    "nombres": ["nombres", "nombre(s)"],
    "apellidos": ["apellidos", "apellido"],
    "edad": ["edad", "edad_anios", "edad en anos", "edad_años"],
    "servicio": ["tipo_servicio", "servicio", "actividad", "tipo de servicio", "estudio"],
    "padecimiento": ["padecimiento", "diagnostico", "diagnóstico"],
    "tipo_evento": ["tipo_registro", "tipo_evento", "tipo de registro", "tipo de evento"],
}

MUNICIPIOS_CONOCIDOS = ["Gómez Farías", "Sayula", "Tuxpan", "Zapotiltic", "Zapotlán el Grande"]
ALIAS_MUNICIPIO = {"ciudad guzman": "Zapotlán el Grande", "cd guzman": "Zapotlán el Grande", "cd. guzman": "Zapotlán el Grande"}

UMBRAL_SIMILITUD = 92
EDAD_MIN, EDAD_MAX = 0, 110
