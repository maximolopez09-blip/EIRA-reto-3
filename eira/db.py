import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import DB_PATH
from .matching import componentes, sugerir

PENDIENTE, VINCULAR, DISTINTAS = "Dejar pendiente", "Vincular", "Personas distintas"
DECISIONES = [PENDIENTE, VINCULAR, DISTINTAS]
COMPARAR = ["fecha", "tipo_evento", "programa", "municipio", "nombre", "edad", "servicio", "padecimiento"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, archivo TEXT, sha256 TEXT, tipo TEXT, filas INTEGER,
    nuevos INTEGER, sin_cambios INTEGER, conflictos INTEGER, importado_en TEXT);
CREATE TABLE IF NOT EXISTS actividades (
    folio TEXT PRIMARY KEY, tipo_evento TEXT, fecha TEXT, fecha_original TEXT, fecha_valida INTEGER,
    programa TEXT, municipio TEXT, nombre TEXT, edad INTEGER, servicio TEXT, padecimiento TEXT,
    archivo_origen TEXT, ubicacion_origen TEXT, metodo TEXT, valores_originales_json TEXT,
    confirmado_en TEXT, import_id INTEGER);
CREATE TABLE IF NOT EXISTS cambios (
    id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT, campo TEXT, valor_anterior TEXT, valor_nuevo TEXT,
    origen TEXT, confirmado_en TEXT);
CREATE TABLE IF NOT EXISTS conflictos_folio (
    id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT, datos_actuales_json TEXT, datos_entrantes_json TEXT,
    archivo TEXT, ubicacion TEXT, estado TEXT, creado_en TEXT, decidido_en TEXT);
CREATE TABLE IF NOT EXISTS sugerencias_identidad (
    folio_a TEXT, folio_b TEXT, puntaje REAL, motivo TEXT, prioridad TEXT, estado TEXT, decidido_en TEXT,
    PRIMARY KEY (folio_a, folio_b));
"""


def ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def conectar(path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def reiniciar(conn: sqlite3.Connection):
    for t in ("imports", "actividades", "cambios", "conflictos_folio", "sugerencias_identidad"):
        conn.execute(f"DELETE FROM {t}")
    conn.commit()


def valores(r) -> dict:
    v = {k: r[k] if k in r.keys() else None for k in COMPARAR}
    v["edad"] = None if v["edad"] in (None, "") else int(v["edad"])
    v["fecha_original"] = None if r["fecha_valida"] else (r["fecha_original"] or None)
    return v


def actividad(conn, folio):
    return conn.execute("SELECT * FROM actividades WHERE folio = ?", (folio,)).fetchone()


def _conflicto_registrado(conn, folio, entrante: dict) -> bool:
    filas = conn.execute("SELECT datos_entrantes_json FROM conflictos_folio WHERE folio = ?", (folio,)).fetchall()
    return any(json.loads(f[0]) == entrante for f in filas)


def clasificar(conn, registros: list[dict]) -> list[str]:
    """Estado que tendría cada registro al guardarse (sin escribir nada)."""
    vistos, estados = {}, []
    for r in registros:
        f = r.get("folio")
        if not f:
            estados.append("Sin folio: no se guardará")
            continue
        previo = vistos.get(f)
        existente = actividad(conn, f)
        base = valores(previo) if previo else (valores(existente) if existente else None)
        if base is None:
            estados.append("Nuevo")
        elif base == valores(r):
            estados.append("Repetido idéntico en el archivo" if previo else "Sin cambios (ya guardado)")
        elif _conflicto_registrado(conn, f, valores(r)):
            estados.append("Conflicto ya registrado")
        else:
            estados.append("Folio existente con datos diferentes: irá a revisión")
        vistos.setdefault(f, r)
    return estados


def confirmar(conn, registros: list[dict], cambios: list[tuple], archivo: str, sha: str, tipo: str) -> dict:
    """Guarda registros confirmados. Mismo folio + mismos datos = sin cambios; datos distintos = conflicto."""
    ts = ahora()
    res = {"nuevos": 0, "sin_cambios": 0, "conflictos": 0, "omitidos": 0}
    cur = conn.execute("INSERT INTO imports (archivo, sha256, tipo, filas, importado_en) VALUES (?,?,?,?,?)",
                       (archivo, sha, tipo, len(registros), ts))
    import_id = cur.lastrowid
    for r in registros:
        f = r.get("folio")
        if not f:
            res["omitidos"] += 1
            continue
        existente = actividad(conn, f)
        if existente is None:
            extra = {"originales": r.get("originales", {}), "nombre_original": r.get("nombre_original", r.get("nombre")),
                     "notas": r.get("notas", []), "extraccion": r.get("extraccion", {})}
            conn.execute(
                """INSERT INTO actividades (folio, tipo_evento, fecha, fecha_original, fecha_valida, programa, municipio,
                nombre, edad, servicio, padecimiento, archivo_origen, ubicacion_origen, metodo, valores_originales_json,
                confirmado_en, import_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f, r["tipo_evento"], r["fecha"], r.get("fecha_original"), int(bool(r["fecha_valida"])), r.get("programa"),
                 r.get("municipio"), r.get("nombre"), r.get("edad"), r.get("servicio"), r.get("padecimiento"),
                 r.get("archivo", archivo), r.get("ubicacion"), r.get("metodo"), json.dumps(extra, ensure_ascii=False),
                 ts, import_id))
            res["nuevos"] += 1
        elif valores(existente) == valores(r):
            res["sin_cambios"] += 1
        elif _conflicto_registrado(conn, f, valores(r)):
            res["sin_cambios"] += 1
        else:
            conn.execute(
                """INSERT INTO conflictos_folio (folio, datos_actuales_json, datos_entrantes_json, archivo, ubicacion,
                estado, creado_en) VALUES (?,?,?,?,?,?,?)""",
                (f, json.dumps(valores(existente), ensure_ascii=False), json.dumps(valores(r), ensure_ascii=False),
                 r.get("archivo", archivo), r.get("ubicacion"), "pendiente", ts))
            res["conflictos"] += 1
    conn.executemany("INSERT INTO cambios (folio, campo, valor_anterior, valor_nuevo, origen, confirmado_en) VALUES (?,?,?,?,?,?)",
                     [(*c, ts) for c in cambios])
    conn.execute("UPDATE imports SET nuevos=?, sin_cambios=?, conflictos=? WHERE id=?",
                 (res["nuevos"], res["sin_cambios"], res["conflictos"], import_id))
    actualizar_sugerencias(conn)
    conn.commit()
    return res


def resolver_conflicto(conn, cid: int, aplicar: bool):
    c = conn.execute("SELECT * FROM conflictos_folio WHERE id = ?", (cid,)).fetchone()
    ts = ahora()
    if aplicar:
        actual, nuevo = json.loads(c["datos_actuales_json"]), json.loads(c["datos_entrantes_json"])
        for campo in COMPARAR:
            if actual.get(campo) != nuevo.get(campo):
                conn.execute(f"UPDATE actividades SET {campo} = ? WHERE folio = ?", (nuevo.get(campo), c["folio"]))
                conn.execute("INSERT INTO cambios (folio, campo, valor_anterior, valor_nuevo, origen, confirmado_en) VALUES (?,?,?,?,?,?)",
                             (c["folio"], campo, _s(actual.get(campo)), _s(nuevo.get(campo)), "resolución de conflicto", ts))
        conn.execute("UPDATE actividades SET fecha_valida = ?, fecha_original = COALESCE(?, fecha_original), archivo_origen = ?, ubicacion_origen = ? WHERE folio = ?",
                     (int(nuevo.get("fecha") is not None), nuevo.get("fecha_original"), c["archivo"], c["ubicacion"], c["folio"]))
    conn.execute("UPDATE conflictos_folio SET estado = ?, decidido_en = ? WHERE id = ?",
                 ("aplicar nuevo" if aplicar else "mantener actual", ts, cid))
    actualizar_sugerencias(conn)
    conn.commit()


def _s(v):
    return None if v is None else str(v)


def actualizar_sugerencias(conn):
    regs = [dict(r) for r in conn.execute("SELECT folio, nombre, edad, municipio FROM actividades")]
    nuevas = {(s["folio_a"], s["folio_b"]): s for s in sugerir(regs)}
    existentes = {(r["folio_a"], r["folio_b"]): r["estado"] for r in conn.execute("SELECT folio_a, folio_b, estado FROM sugerencias_identidad")}
    for k, estado in existentes.items():
        if k not in nuevas and estado == PENDIENTE:
            conn.execute("DELETE FROM sugerencias_identidad WHERE folio_a=? AND folio_b=?", k)
    for k, s in nuevas.items():
        if k in existentes:
            conn.execute("UPDATE sugerencias_identidad SET puntaje=?, motivo=?, prioridad=? WHERE folio_a=? AND folio_b=?",
                         (s["puntaje"], s["motivo"], s["prioridad"], *k))
        else:
            conn.execute("INSERT INTO sugerencias_identidad VALUES (?,?,?,?,?,?,NULL)",
                         (*k, s["puntaje"], s["motivo"], s["prioridad"], PENDIENTE))


def guardar_decisiones(conn, decisiones: list[tuple[str, str, str]]) -> int:
    """decisiones: [(folio_a, folio_b, estado)]. Solo una persona decide; se registra en la bitácora."""
    ts, n = ahora(), 0
    for a, b, estado in decisiones:
        previo = conn.execute("SELECT estado FROM sugerencias_identidad WHERE folio_a=? AND folio_b=?", (a, b)).fetchone()
        if previo is None or previo[0] == estado:
            continue
        conn.execute("UPDATE sugerencias_identidad SET estado=?, decidido_en=? WHERE folio_a=? AND folio_b=?",
                     (estado, None if estado == PENDIENTE else ts, a, b))
        conn.execute("INSERT INTO cambios (folio, campo, valor_anterior, valor_nuevo, origen, confirmado_en) VALUES (?,?,?,?,?,?)",
                     (f"{a} ↔ {b}", "identidad", previo[0], estado, "revisión de identidad", ts))
        n += 1
    conn.commit()
    return n


def df(conn, sql: str, params=()) -> pd.DataFrame:
    filas = conn.execute(sql, params).fetchall()
    cols = [d[0] for d in conn.execute(sql, params).description] if not filas else filas[0].keys()
    return pd.DataFrame([dict(f) for f in filas], columns=list(cols))


def actividades_df(conn) -> pd.DataFrame:
    return df(conn, "SELECT * FROM actividades ORDER BY folio")


def sugerencias_df(conn) -> pd.DataFrame:
    return df(conn, """SELECT s.*, a.nombre AS nombre_a, a.edad AS edad_a, a.municipio AS municipio_a,
        json_extract(a.valores_originales_json, '$.nombre_original') AS original_a,
        json_extract(b.valores_originales_json, '$.nombre_original') AS original_b,
        a.archivo_origen || ', ' || a.ubicacion_origen AS fuente_a,
        b.nombre AS nombre_b, b.edad AS edad_b, b.municipio AS municipio_b,
        b.archivo_origen || ', ' || b.ubicacion_origen AS fuente_b
        FROM sugerencias_identidad s JOIN actividades a ON a.folio = s.folio_a JOIN actividades b ON b.folio = s.folio_b
        ORDER BY s.prioridad, s.folio_a, s.folio_b""")


def conflictos_df(conn, pendientes: bool = True) -> pd.DataFrame:
    return df(conn, "SELECT * FROM conflictos_folio" + (" WHERE estado = 'pendiente'" if pendientes else "") + " ORDER BY folio, id")


def cambios_df(conn) -> pd.DataFrame:
    return df(conn, "SELECT folio, campo, valor_anterior, valor_nuevo, origen, confirmado_en FROM cambios ORDER BY id")


def imports_df(conn) -> pd.DataFrame:
    return df(conn, "SELECT archivo, tipo, filas, nuevos, sin_cambios, conflictos, importado_en FROM imports ORDER BY id")


def extra(valores_json) -> dict:
    try:
        return json.loads(valores_json or "{}")
    except (TypeError, ValueError):
        return {}


def identidades_pendientes(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM sugerencias_identidad WHERE estado = ?", (PENDIENTE,)).fetchone()[0]


def mapa_personas(conn) -> dict[str, str]:
    folios = [r[0] for r in conn.execute("SELECT folio FROM actividades")]
    vinc = [(r[0], r[1]) for r in conn.execute("SELECT folio_a, folio_b FROM sugerencias_identidad WHERE estado = ?", (VINCULAR,))]
    return componentes(folios, vinc)
