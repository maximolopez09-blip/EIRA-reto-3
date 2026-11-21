import io

import pandas as pd

from .config import ATENCION, CITA, PARTICIPACION, SINONIMOS
from .quality import norm, normalizar_municipio, normalizar_nombre, original, parse_edad, parse_fecha, texto, vacio


def leer_tabla(nombre: str, contenido: bytes) -> dict[str, pd.DataFrame]:
    """Hojas del archivo como DataFrames de texto/objetos sin conversión de tipos."""
    if nombre.lower().endswith(".csv"):
        for enc in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(contenido), dtype=str, keep_default_na=False, sep=None, engine="python", encoding=enc)
                return {"CSV": df}
            except UnicodeDecodeError:
                continue
        raise ValueError("No se pudo leer el CSV (codificación desconocida)")
    hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None, dtype=object)
    return {k: v for k, v in hojas.items() if not v.empty}


def proponer_mapeo(columnas) -> dict[str, str | None]:
    cols = {norm(c).replace(" ", "_"): c for c in columnas}
    cols.update({norm(c): c for c in columnas})
    mapeo = {}
    for campo, sinonimos in SINONIMOS.items():
        mapeo[campo] = next((cols[k] for s in sinonimos for k in (norm(s), norm(s).replace(" ", "_")) if k in cols), None)
    if mapeo.get("nombre") and mapeo["nombre"] in (mapeo.get("nombres"), mapeo.get("apellidos")):
        mapeo["nombre"] = None
    if mapeo.get("nombres"):
        mapeo["nombre"] = None
    return mapeo


def inferir_tipo_evento(columnas, archivo: str = "") -> str:
    n = " ".join(norm(c) for c in columnas) + " " + norm(archivo)
    return PARTICIPACION if ("particip" in n or "dia_evento" in n) else ATENCION


def tipo_desde_valor(v, defecto: str) -> str:
    n = norm(v)
    if "cita" in n:
        return CITA
    if "particip" in n:
        return PARTICIPACION
    if "atenc" in n:
        return ATENCION
    return defecto


def registros_automaticos(nombre: str, contenido: bytes) -> list[dict]:
    """Lectura con el mapeo propuesto (primera hoja). La app permite revisarlo antes de usarlo."""
    hoja, frame = next(iter(leer_tabla(nombre, contenido).items()))
    return aplicar_mapeo(frame, proponer_mapeo(frame.columns), inferir_tipo_evento(frame.columns, nombre), nombre, hoja)


def aplicar_mapeo(df: pd.DataFrame, mapeo: dict, tipo_defecto: str, archivo: str, hoja: str | None = None) -> list[dict]:
    """Convierte cada fila en un registro propuesto con valor original y procedencia."""
    def col(row, campo):
        c = mapeo.get(campo)
        return row[c] if c else None

    registros = []
    for i, row in df.iterrows():
        if all(vacio(v) for v in row.values):
            continue
        if mapeo.get("nombres") or mapeo.get("apellidos"):
            nombre = " ".join(texto(x) for x in (col(row, "nombres"), col(row, "apellidos")) if texto(x))
        else:
            nombre = texto(col(row, "nombre"))
        fecha_raw = col(row, "fecha")
        fecha, valida = parse_fecha(fecha_raw)
        municipio, nota_mun = normalizar_municipio(col(row, "municipio"))
        ubicacion = f"fila {int(i) + 2}" + (f" (hoja {hoja})" if hoja and hoja != "CSV" else "")
        registros.append({
            "folio": texto(col(row, "folio")).upper(),
            "fecha": fecha,
            "fecha_original": original(fecha_raw),
            "fecha_valida": valida,
            "tipo_evento": tipo_desde_valor(col(row, "tipo_evento"), tipo_defecto) if mapeo.get("tipo_evento") else tipo_defecto,
            "programa": texto(col(row, "programa")) or None,
            "municipio": municipio,
            "nombre": normalizar_nombre(nombre) or None,
            "edad": parse_edad(col(row, "edad")),
            "servicio": texto(col(row, "servicio")) or None,
            "padecimiento": texto(col(row, "padecimiento")) or None,
            "archivo": archivo,
            "ubicacion": ubicacion,
            "metodo": "columna",
            "nombre_original": nombre,
            "notas": [nota_mun] if nota_mun else [],
            "originales": {str(k): original(v) for k, v in row.items()},
        })
    return registros
