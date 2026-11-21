import re
import unicodedata
from datetime import date, datetime, timedelta

from .config import ALIAS_MUNICIPIO, CITA, EDAD_MAX, EDAD_MIN, MUNICIPIOS_CONOCIDOS


def vacio(v) -> bool:
    if v is None:
        return True
    try:
        if v != v:  # NaN / NaT
            return True
    except Exception:
        pass
    return str(v).strip() == ""


def texto(v) -> str:
    return "" if vacio(v) else " ".join(str(v).split())


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", texto(s).lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def original(v) -> str:
    if vacio(v):
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y") if v.time() == datetime.min.time() else v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def parse_fecha(v):
    """Devuelve (fecha ISO o None, válida). Nunca corrige una fecha imposible."""
    if vacio(v):
        return None, False
    if isinstance(v, datetime):
        return v.date().isoformat(), True
    if isinstance(v, date):
        return v.isoformat(), True
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 <= v <= 80000:  # número de serie de Excel
            return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat(), True
        return None, False
    s = str(v).strip()
    if re.fullmatch(r"\d{5}(\.0+)?", s):
        return parse_fecha(float(s))
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})", s)
        if not m:
            return None, False
        d, mo, y = map(int, m.groups())
        if y < 100:
            y += 2000
    try:
        return date(y, mo, d).isoformat(), True
    except ValueError:
        return None, False


def parse_edad(v):
    if vacio(v):
        return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def normalizar_municipio(v):
    """Devuelve (municipio propuesto o None, nota)."""
    s = texto(v)
    if not s:
        return None, ""
    n = norm(s)
    for m in MUNICIPIOS_CONOCIDOS:
        if norm(m) == n:
            return m, ""
    if n in ALIAS_MUNICIPIO:
        return ALIAS_MUNICIPIO[n], f"«{s}» se propuso como {ALIAS_MUNICIPIO[n]}"
    for m in MUNICIPIOS_CONOCIDOS:
        if norm(m) in n:
            return m, f"«{s}» se propuso como {m}"
    return s, "Municipio no reconocido en el catálogo"


def normalizar_nombre(v) -> str:
    s = texto(v)
    return s.title() if s.isupper() else s


def banderas(r: dict, hoy: date | None = None) -> list[str]:
    hoy = hoy or date.today()
    out = []
    if vacio(r.get("folio")):
        out.append("Sin folio")
    if not r.get("fecha_valida"):
        out.append("Fecha inválida" if r.get("fecha_original") else "Sin fecha")
    elif r.get("fecha") and date.fromisoformat(r["fecha"]) > hoy and r.get("tipo_evento") != CITA:
        out.append("Fecha futura")
    if vacio(r.get("municipio")):
        out.append("Sin municipio")
    edad = r.get("edad")
    if edad is not None and not vacio(edad) and not (EDAD_MIN <= int(edad) <= EDAD_MAX):
        out.append("Edad fuera de rango")
    if vacio(r.get("nombre")):
        out.append("Sin nombre")
    return out
