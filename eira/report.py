import io
from datetime import date, datetime

import pandas as pd
from fpdf import FPDF

from . import db
from .config import ATENCION, CITA, PARTICIPACION, SIN_MUNICIPIO

CAMPOS_RESERVADOS = {"nombre", "edad", "padecimiento"}


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["municipio_vista"] = df["municipio"].fillna("").replace("", SIN_MUNICIPIO) if len(df) else []
    df["programa_vista"] = df["programa"].fillna("").replace("", "Sin programa") if len(df) else []
    return df


def filtrar(df: pd.DataFrame, municipios=None, programas=None, rango=None):
    """Devuelve (filtrado, nº excluidas por fecha inválida). Sin rango, las fechas inválidas cuentan."""
    df = preparar(df)
    if municipios:
        df = df[df["municipio_vista"].isin(municipios)]
    if programas:
        df = df[df["programa_vista"].isin(programas)]
    excluidas = 0
    if rango:
        validas = df["fecha_valida"].astype(bool) & df["fecha"].notna()
        excluidas = int((~validas).sum())
        d1, d2 = (d.isoformat() for d in rango)
        df = df[validas & (df["fecha"] >= d1) & (df["fecha"] <= d2)]
    return df, excluidas


def resumen(df_f: pd.DataFrame, personas: dict, pendientes: int) -> dict:
    cuenta = df_f["tipo_evento"].value_counts() if len(df_f) else pd.Series(dtype=int)
    reps = {personas.get(f, f) for f in df_f["folio"]} if len(df_f) else set()
    por_mun = (df_f.groupby(["municipio_vista", "tipo_evento"]).size().unstack(fill_value=0)
               if len(df_f) else pd.DataFrame())
    for t in (ATENCION, PARTICIPACION):
        if t not in por_mun.columns:
            por_mun[t] = 0
    return {
        "atenciones": int(cuenta.get(ATENCION, 0)),
        "participaciones": int(cuenta.get(PARTICIPACION, 0)),
        "citas": int(cuenta.get(CITA, 0)),
        "total": int(len(df_f)),
        "unicas": None if pendientes else len(reps),
        "pendientes": pendientes,
        "por_municipio": por_mun.reset_index().rename(columns={"municipio_vista": "Municipio"}) if len(por_mun) else por_mun,
    }


def advertencias(conn, df_all: pd.DataFrame) -> list[str]:
    out = []
    df_all = preparar(df_all)
    for _, r in df_all.iterrows():
        if not r["fecha_valida"]:
            out.append(f"{r['folio']}: fecha inválida (valor original «{r['fecha_original'] or 'vacío'}»); cuenta en el total general y se excluye de filtros por fecha.")
        elif r["fecha"] and r["fecha"] > date.today().isoformat():
            out.append(f"{r['folio']}: fecha futura ({r['fecha']}).")
        if r["municipio_vista"] == SIN_MUNICIPIO:
            out.append(f"{r['folio']}: municipio faltante; se agrupa en «{SIN_MUNICIPIO}».")
        if pd.notna(r["edad"]) and not 0 <= int(r["edad"]) <= 110:
            out.append(f"{r['folio']}: edad fuera de rango.")
    conf = db.conflictos_df(conn)
    if len(conf):
        out.append(f"{len(conf)} folio(s) llegaron con datos diferentes y esperan revisión: {', '.join(sorted(set(conf['folio'])))}.")
    pend = db.identidades_pendientes(conn)
    if pend:
        out.append(f"{pend} posible(s) coincidencia(s) de identidad pendientes: total de beneficiarias únicas pendiente de validación.")
    return out


def fuentes(conn) -> pd.DataFrame:
    imp = db.imports_df(conn)
    if not len(imp):
        return imp
    return imp.rename(columns={"archivo": "Archivo", "tipo": "Tipo", "filas": "Filas leídas", "nuevos": "Nuevos",
                               "sin_cambios": "Sin cambios", "conflictos": "Conflictos", "importado_en": "Importado"})


def ajustes(conn) -> pd.DataFrame:
    c = db.cambios_df(conn)
    if not len(c):
        return c
    reservado = c["campo"].isin(CAMPOS_RESERVADOS)
    c.loc[reservado, ["valor_anterior", "valor_nuevo"]] = "(reservado)"
    return c.rename(columns={"folio": "Folio", "campo": "Campo", "valor_anterior": "Valor anterior", "valor_nuevo": "Valor nuevo",
                             "origen": "Origen", "confirmado_en": "Confirmado"})


def contexto(conn, filtros: dict, res: dict, excluidas: int) -> dict:
    corte = filtros["rango"][1] if filtros.get("rango") else date.today()
    return {
        "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "corte": corte.strftime("%d/%m/%Y"),
        "filtros": [
            ("Municipio", ", ".join(filtros.get("municipios") or []) or "Todos"),
            ("Programa", ", ".join(filtros.get("programas") or []) or "Todos"),
            ("Periodo", " a ".join(d.strftime("%d/%m/%Y") for d in filtros["rango"]) if filtros.get("rango") else "Todo el periodo"),
        ],
        "conteos": [
            ("Atenciones", res["atenciones"]),
            ("Participaciones", res["participaciones"]),
            ("Citas agendadas (no suman a atenciones)", res["citas"]),
            ("Total de actividades", res["total"]),
            ("Beneficiarias únicas", res["unicas"] if res["unicas"] is not None else "Pendiente de validación"),
            ("Actividades con fecha inválida excluidas por el filtro de periodo", excluidas),
        ],
        "por_municipio": res["por_municipio"],
        "fuentes": fuentes(conn),
        "advertencias": advertencias(conn, db.actividades_df(conn)),
        "ajustes": ajustes(conn),
    }


def excel_bytes(ctx: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        filas = [("Informe agregado EIRA – Impacto social", ""), ("Generado", ctx["generado"]), ("Fecha de corte", ctx["corte"]), ("", "")]
        filas += [("Filtro: " + k, v) for k, v in ctx["filtros"]] + [("", "")] + ctx["conteos"]
        pd.DataFrame(filas, columns=["Concepto", "Valor"]).to_excel(xw, sheet_name="Resumen", index=False)
        ctx["por_municipio"].to_excel(xw, sheet_name="Por municipio", index=False)
        ctx["fuentes"].to_excel(xw, sheet_name="Fuentes", index=False)
        pd.DataFrame({"Advertencia": ctx["advertencias"] or ["Sin advertencias"]}).to_excel(xw, sheet_name="Advertencias", index=False)
        (ctx["ajustes"] if len(ctx["ajustes"]) else pd.DataFrame({"Ajustes": ["Sin ajustes manuales"]})).to_excel(xw, sheet_name="Ajustes manuales", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(80, max(12, *(len(str(c.value or "")) + 2 for c in col)))
    return buf.getvalue()


def _lat(s) -> str:
    return str(s).replace("–", "-").replace("↔", "<->").encode("latin-1", "replace").decode("latin-1")


def pdf_bytes(ctx: dict) -> bytes:
    pdf = FPDF(format="Letter")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 9, _lat("Informe agregado EIRA - Impacto social"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, _lat(f"Generado: {ctx['generado']}   |   Fecha de corte: {ctx['corte']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, _lat("Sin nombres ni datos de salud. Cifras calculadas desde los registros confirmados."), new_x="LMARGIN", new_y="NEXT")

    def titulo(t):
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _lat(t), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)

    def tabla(frame: pd.DataFrame):
        if not len(frame):
            pdf.cell(0, 5, "Sin datos", new_x="LMARGIN", new_y="NEXT")
            return
        with pdf.table(text_align="LEFT", line_height=4.5) as t:
            t.row([_lat(c) for c in frame.columns])
            for _, r in frame.iterrows():
                t.row([_lat("" if pd.isna(v) else v) for v in r.values])

    titulo("Filtros aplicados")
    tabla(pd.DataFrame(ctx["filtros"], columns=["Filtro", "Valor"]))
    titulo("Conteos")
    tabla(pd.DataFrame(ctx["conteos"], columns=["Indicador", "Valor"]))
    titulo("Actividades por municipio")
    tabla(ctx["por_municipio"])
    titulo("Fuentes")
    tabla(ctx["fuentes"])
    titulo("Advertencias de calidad")
    for a in ctx["advertencias"] or ["Sin advertencias"]:
        pdf.multi_cell(0, 4.5, _lat("- " + a), new_x="LMARGIN", new_y="NEXT")
    titulo("Ajustes manuales (trazabilidad)")
    tabla(ctx["ajustes"])
    return bytes(pdf.output())
