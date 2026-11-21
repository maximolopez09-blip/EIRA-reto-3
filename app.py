import hashlib
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from eira import config, db, report
from eira.config import CITA, DATOS, EJEMPLOS, NO_REGISTRADO, SIN_MUNICIPIO, TIPOS_EVENTO
from eira.matching import PRIORIDAD_ALTA, PRIORIDAD_HOMONIMAS, PRIORIDAD_REVISAR
from eira.quality import banderas, normalizar_municipio, parse_edad, parse_fecha, texto, vacio
from eira.tabular import aplicar_mapeo, inferir_tipo_evento, leer_tabla, proponer_mapeo

st.set_page_config(page_title="EIRA · Impacto social", page_icon=":material/volunteer_activism:", layout="wide",
                   initial_sidebar_state="collapsed")

EDITABLES = ["folio", "fecha", "tipo_evento", "programa", "municipio", "nombre", "edad", "servicio", "padecimiento"]
NOMBRES_CAMPO = {"folio": "Folio de la actividad", "fecha": "Fecha (dd/mm/aaaa)", "tipo_evento": "Tipo de registro",
                 "programa": "Programa", "municipio": "Municipio", "nombre": "Nombre completo", "edad": "Edad",
                 "servicio": "Servicio o actividad", "padecimiento": "Padecimiento (solo si viene escrito)",
                 "nombres": "Nombre(s)", "apellidos": "Apellidos"}
TABULARES, DOCUMENTOS = (".xlsx", ".csv"), (".pdf", ".png", ".jpg", ".jpeg")
PASOS = ["Cargar archivos", "Revisar datos", "Confirmar", "Ver tablero"]
SIN_ASIGNAR = "(no está en el archivo)"
MAX_TARJETAS = 25

ss = st.session_state
for k, v in {"pagina": "tablero", "lotes": {}, "contador": 0, "subida": 0, "flash": [], "saltadas": set()}.items():
    ss.setdefault(k, v)


@st.cache_resource
def conexion(ruta: str):
    return db.conectar(ruta)


conn = conexion(str(config.DB_PATH))

# Textos del cargador de archivos en español (Streamlit no permite cambiarlos desde Python).
st.html("""<style>
.st-key-zona_subida [data-testid="stFileUploaderDropzoneInstructions"] {font-size: 0}
.st-key-zona_subida [data-testid="stFileUploaderDropzoneInstructions"]::after {
  content: "Arrastra aquí tus archivos · Excel, CSV, PDF, PNG o JPG"; font-size: 0.95rem}
.st-key-zona_subida [data-testid="stFileUploaderDropzone"] button {font-size: 0}
.st-key-zona_subida [data-testid="stFileUploaderDropzone"] button::after {content: "Elegir archivos"; font-size: 1rem}
</style>""")


# ------------------------------------------------------------------ utilidades
def ir(pagina: str):
    ss.pagina = pagina


def fecha_vista(r) -> str:
    if r.get("fecha_valida") and r.get("fecha"):
        return date.fromisoformat(r["fecha"]).strftime("%d/%m/%Y")
    return r.get("fecha_original") or ""


def tx(v, defecto: str = "") -> str:
    return defecto if vacio(v) else str(v)


def vista(r, campo) -> str:
    if campo == "fecha":
        return fecha_vista(r)
    v = r.get(campo)
    return "" if vacio(v) else str(v)


def aplicar_valor(r: dict, campo: str, valor: str):
    valor = texto(valor)
    if campo == "fecha":
        r["fecha"], r["fecha_valida"] = parse_fecha(valor)
        r["fecha_original"] = valor
    elif campo == "edad":
        r["edad"] = parse_edad(valor)
    elif campo == "municipio":
        r["municipio"] = normalizar_municipio(valor)[0]
    elif campo == "folio":
        r["folio"] = valor.upper()
    else:
        r[campo] = valor or None


def preparar(registros: list[dict]) -> list[dict]:
    for r in registros:
        r["_prop"] = {c: vista(r, c) for c in EDITABLES}
    return registros


def estado_campo(prop: str, ahora_v: str) -> str:
    if prop and ahora_v == prop:
        return "Extraído automáticamente"
    if prop:
        return "Corregido en revisión"
    return "Captura manual" if ahora_v else "Sin dato"


def problemas(r) -> list[tuple[str, str]]:
    """Problemas del valor propuesto, en lenguaje simple: (campo, mensaje)."""
    out = []
    for b in banderas(r):
        if b == "Sin folio":
            out.append(("folio", "Falta el folio de la actividad. Sin folio no se puede guardar."))
        elif b == "Fecha inválida":
            out.append(("fecha", f"La fecha «{r.get('fecha_original')}» no existe en el calendario. Corrígela o déjala así: "
                                 "contará en el total, pero no en los filtros por fecha."))
        elif b == "Sin fecha":
            out.append(("fecha", "No tiene fecha. Contará en el total, pero no en los filtros por fecha."))
        elif b == "Fecha futura":
            out.append(("fecha", f"La fecha {fecha_vista(r)} es posterior a hoy. Revísala."))
        elif b == "Sin municipio":
            out.append(("municipio", f"Falta el municipio. Si lo dejas vacío, se contará en «{SIN_MUNICIPIO}»."))
        elif b == "Edad fuera de rango":
            out.append(("edad", f"La edad «{r.get('edad')}» parece un error de captura."))
        elif b == "Sin nombre":
            out.append(("nombre", "Falta el nombre de la persona."))
    for n in r.get("notas", []):
        if not n.startswith("Lectura dudosa"):  # esas se muestran junto a la imagen del documento
            out.append(("municipio", f"{n}. Confírmalo."))
    return out


def resumen_tipos(regs) -> str:
    cuenta = pd.Series([r["tipo_evento"] for r in regs]).value_counts()
    plural = {"Atención": "atenciones", "Participación": "participaciones", CITA: "citas agendadas"}
    return " y ".join(f"{n} {plural[t] if n != 1 else t.lower()}" for t, n in cuenta.items()) or "0 registros"


def unir_pagina(lote: dict) -> bool:
    """Si el archivo es otra página suelta de un formato ya cargado (p. ej. la foto del reverso), se une a ese documento."""
    from eira import documents
    f = lote["doc"].get("formulario")
    for otro in ss.lotes.values():
        g = otro.get("doc", {}).get("formulario") if otro.get("tipo") in ("pdf", "imagen") else None
        if f and g and g["formato"] == f["formato"] and not set(g["paginas"]) & set(f["paginas"]) and 0 in set(g["paginas"]) | set(f["paginas"]):
            otro["partes"] = sorted(otro["partes"] + lote["partes"])
            otro["archivo"] = otro["partes"][0][1]
            otro["doc"] = documents.procesar_varios([(n, c) for _, n, c in otro["partes"]])
            otro["registros"] = preparar([documents.a_registro(otro["doc"], otro["archivo"])])
            otro["shas"] = otro.get("shas", []) + [lote["sha"]]
            otro["version"] += 1
            ss.flash.append(("info", f"«{lote['archivo']}» se unió a «{otro['archivo']}»: son páginas del mismo formato."))
            return True
    return False


def nuevo_lote(nombre: str, contenido: bytes):
    sha = hashlib.sha256(contenido).hexdigest()
    if any(sha in (l["sha"], *l.get("shas", [])) for l in ss.lotes.values()):
        ss.flash.append(("info", f"«{nombre}» ya estaba en la lista."))
        return
    ss.contador += 1
    lote = {"id": ss.contador, "archivo": nombre, "sha": sha, "registros": None, "version": 0}
    low = nombre.lower()
    try:
        if low.endswith(TABULARES):
            lote["tipo"] = "csv" if low.endswith(".csv") else "excel"
            lote["hojas"] = leer_tabla(nombre, contenido)
            if not lote["hojas"]:
                raise ValueError("el archivo no tiene filas")
            lote["hoja"] = next(iter(lote["hojas"]))
            cols = [str(c) for c in lote["hojas"][lote["hoja"]].columns]
            lote["mapeo"] = proponer_mapeo(cols)
            lote["tipo_defecto"] = inferir_tipo_evento(cols, nombre)
            aplicar_lote(lote)
        elif low.endswith(DOCUMENTOS):
            from eira import documents
            lote["tipo"] = "pdf" if low.endswith(".pdf") else "imagen"
            lote["doc"] = documents.procesar(nombre, contenido)
            lote["partes"] = [(((lote["doc"].get("formulario") or {}).get("paginas") or [0])[0], nombre, contenido)]
            if unir_pagina(lote):
                return
            lote["registros"] = preparar([documents.a_registro(lote["doc"], nombre)])
        else:
            ss.flash.append(("error", f"No podemos leer archivos de este tipo: {nombre}"))
            return
    except Exception as e:
        ss.flash.append(("error", f"No pudimos leer «{nombre}»: {e}"))
        return
    ss.lotes[lote["id"]] = lote


def aplicar_lote(lote):
    m = lote["mapeo"]
    if not m.get("folio"):
        lote["registros"] = None
        return
    frame = lote["hojas"][lote["hoja"]]
    lote["registros"] = preparar(aplicar_mapeo(frame, m, lote["tipo_defecto"], lote["archivo"], lote["hoja"]))
    lote["version"] += 1


def faltantes(lote) -> list[str]:
    m = lote["mapeo"]
    falta = [c for c in ("folio", "fecha", "municipio") if not m.get(c)]
    if not (m.get("nombre") or m.get("nombres")):
        falta.append("nombre")
    return falta


def cargar_ejemplo(*archivos):
    for a in archivos:
        p = DATOS / a if (DATOS / a).exists() else EJEMPLOS / a
        nuevo_lote(p.name, p.read_bytes())
    ss.pagina = "cargar"


def quitar_lote(lid):
    ss.lotes.pop(lid, None)


def lotes_listos():
    return [l for l in ss.lotes.values() if l.get("registros")]


def registros_finales(lote) -> tuple[list[dict], list[tuple]]:
    regs, cambios = [], []
    for r in lote["registros"]:
        r2 = {k: v for k, v in r.items() if k != "_prop"}
        if lote["tipo"] in ("pdf", "imagen"):
            r2["extraccion"] = {c: estado_campo(r["_prop"][c], vista(r, c)) for c in EDITABLES}
            if not (r2.get("folio") and r2.get("nombre")):
                r2["folio"] = ""
        for c in EDITABLES:
            antes, ahora_v = r["_prop"][c], vista(r, c)
            if antes != ahora_v and r2["folio"]:
                cambios.append((r2["folio"], c, antes or None, ahora_v or None,
                                "captura manual" if not antes else "corrección en revisión"))
        regs.append(r2)
    return regs, cambios


def campo_editable(lote, i, r, campo, contenedor=st):
    key = f"c_{lote['id']}_v{lote['version']}_{i}_{campo}"
    if campo == "tipo_evento":
        val = contenedor.selectbox(NOMBRES_CAMPO[campo], TIPOS_EVENTO, index=TIPOS_EVENTO.index(r["tipo_evento"]),
                                   key=key, persist_state="session")
    else:
        val = contenedor.text_input(NOMBRES_CAMPO[campo], value=vista(r, campo), key=key, persist_state="session",
                                    placeholder=NO_REGISTRADO if campo == "padecimiento" else "Escribe el dato")
    if texto(val) != vista(r, campo):
        aplicar_valor(r, campo, val)
    return estado_campo(r["_prop"][campo], vista(r, campo))


def pasos(actual: int):
    st.progress(actual / len(PASOS), text=f"Paso {actual} de {len(PASOS)} · {PASOS[actual - 1]}")
    fila = st.container(horizontal=True, gap="large")
    for i, p in enumerate(PASOS, 1):
        icono = ":material/check_circle:" if i < actual else (":material/radio_button_checked:" if i == actual else ":material/radio_button_unchecked:")
        fila.markdown(f"{icono} **{p}**" if i == actual else f"{icono} {p}")


def mostrar_avisos():
    for nivel, msg in ss.flash:
        getattr(st, nivel)(msg)
    ss.flash = []


def decidir(a, b, estado):
    db.guardar_decisiones(conn, [(a, b, estado)])


def saltar(a, b):
    ss.saltadas = ss.saltadas | {(a, b)}


def resolver(cid, aplicar):
    db.resolver_conflicto(conn, cid, aplicar=aplicar)


def reiniciar_demo():
    db.reiniciar(conn)
    for k in list(ss.keys()):
        del ss[k]


# ------------------------------------------------------------------ barra lateral
with st.sidebar:
    st.subheader("EIRA · Movimiento Rosa")
    st.caption("Prototipo local con datos ficticios · Reto 3: impacto social")
    with st.expander("Reiniciar demo", icon=":material/restart_alt:"):
        st.write("Borra todas las actividades, decisiones y la bitácora guardadas en este equipo.")
        ok = st.checkbox("Entiendo que se borrará todo", key="ok_reinicio")
        st.button("Borrar todo y empezar de nuevo", type="primary", disabled=not ok, on_click=reiniciar_demo, key="reiniciar")

pagina = ss.pagina

# ------------------------------------------------------------------ 4. Tablero (inicio)
if pagina == "tablero":
    st.title("Impacto social de EIRA")
    mostrar_avisos()
    todo = db.actividades_df(conn)
    acciones = st.container(horizontal=True)
    acciones.button("Agregar datos", icon=":material/add:", type="primary", on_click=ir, args=("cargar",), key="nav_agregar")
    if not len(todo):
        st.info("Empieza agregando tus archivos de atenciones y participaciones, o prueba con los datos de ejemplo.",
                title="Aún no hay datos", icon=":material/info:")
        acciones.button("Probar con datos de ejemplo", icon=":material/science:", key="ej_inicio",
                        on_click=cargar_ejemplo, args=("atenciones.xlsx", "participaciones.xlsx"))
        st.stop()
    acciones.button("Buscar beneficiaria", icon=":material/search:", on_click=ir, args=("buscar",), key="nav_buscar")
    informe = acciones.popover("Descargar informe", icon=":material/download:")

    pend, conf = db.identidades_pendientes(conn), len(db.conflictos_df(conn))
    if pend or conf:
        partes = ([f"{pend} posibles coincidencias entre personas"] if pend else []) + ([f"{conf} folios repetidos con datos distintos"] if conf else [])
        aviso = st.container(border=True, horizontal=True, vertical_alignment="center")
        aviso.markdown(f":orange[:material/pending_actions:] **Hay información por revisar:** {' y '.join(partes)}.  \n"
                       "Mientras tanto, el total de beneficiarias únicas queda pendiente de validación.")
        aviso.button("Revisar ahora", icon=":material/fact_check:", on_click=ir, args=("pendientes",), key="ir_pendientes")

    base = report.preparar(todo)
    with st.container(border=True):
        f = st.columns([2, 2, 2, 2], vertical_alignment="bottom")
        municipios = f[0].multiselect("Municipio", sorted(base["municipio_vista"].unique()), placeholder="Todos", key="f_mun")
        programas = f[1].multiselect("Programa", sorted(base["programa_vista"].unique()), placeholder="Todos", key="f_prog")
        modo = f[2].segmented_control("Periodo", ["Todo", "Elegir fechas"], default="Todo", required=True, key="f_modo")
        rango = None
        if modo == "Elegir fechas":
            fechas = pd.to_datetime(base.loc[base["fecha_valida"] == 1, "fecha"])
            ini, fin = (fechas.min().date(), fechas.max().date()) if len(fechas) else (date.today(), date.today())
            sel = f[3].date_input("Desde / hasta", (ini, fin), format="DD/MM/YYYY", key="f_rango")
            rango = tuple(sel) if isinstance(sel, (tuple, list)) and len(sel) == 2 else None
    filtros = {"municipios": municipios, "programas": programas, "rango": rango}
    df_f, excluidas = report.filtrar(todo, **filtros)
    res = report.resumen(df_f, db.mapa_personas(conn), pend)

    k = st.columns(4 if res["citas"] else 3)
    k[0].metric("Atenciones", res["atenciones"], border=True, icon=":material/medical_services:")
    k[1].metric("Participaciones", res["participaciones"], border=True, icon=":material/groups:")
    k[2].metric("Beneficiarias únicas", res["unicas"] if res["unicas"] is not None else "Pendiente", border=True,
                icon=":material/person:", help="Se calcula cuando terminas de revisar las posibles coincidencias entre personas.")
    if res["citas"]:
        k[3].metric("Citas agendadas", res["citas"], border=True, icon=":material/event:",
                    help="Solo registros que la fuente identifica como cita. No suman a atenciones.")
    if excluidas:
        st.caption(f":material/info: {excluidas} actividad(es) con fecha inválida no aparecen en este periodo, pero sí en el total general.")

    pm = res["por_municipio"]
    if len(pm):
        largo = pm.melt(id_vars="Municipio", var_name="Tipo", value_name="Actividades")
        largo = largo[largo["Actividades"] > 0]
        graf = (alt.Chart(largo, title="Actividades por municipio").mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(x=alt.X("Municipio:N", sort="-y", title=None, axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("Actividades:Q", title=None), color=alt.Color("Tipo:N", title=None, legend=alt.Legend(orient="top")),
                        xOffset="Tipo:N", tooltip=["Municipio", "Tipo", "Actividades"]).properties(height=340))
        st.altair_chart(graf, alt="Gráfica de barras de atenciones y participaciones por municipio")

    adv = report.advertencias(conn, todo)
    with st.expander(f"Avisos de calidad ({len(adv)})", icon=":material/report:"):
        for a in adv:
            st.markdown(f"- {a}")
        if not adv:
            st.write("Sin avisos.")
    with st.expander("Fuentes y bitácora de cambios", icon=":material/history:"):
        st.markdown("**Archivos cargados**")
        st.dataframe(report.fuentes(conn), hide_index=True, alt="Archivos cargados")
        bit = db.cambios_df(conn)
        st.markdown("**Cambios y decisiones**")
        if len(bit):
            st.dataframe(bit.rename(columns={"folio": "Folio", "campo": "Campo", "valor_anterior": "Antes", "valor_nuevo": "Después",
                                             "origen": "Origen", "confirmado_en": "Fecha y hora"}), hide_index=True, alt="Bitácora")
        else:
            st.caption("Todavía no hay cambios registrados.")

    with informe:
        st.caption("Con los filtros aplicados. No incluye nombres ni datos de salud.")
        ctx = report.contexto(conn, filtros, res, excluidas)
        hoy = date.today().strftime("%Y%m%d")
        st.download_button("Excel", report.excel_bytes(ctx), f"informe_eira_{hoy}.xlsx", icon=":material/table_view:",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch", key="dl_xlsx")
        st.download_button("PDF", report.pdf_bytes(ctx), f"informe_eira_{hoy}.pdf", icon=":material/picture_as_pdf:",
                           mime="application/pdf", width="stretch", key="dl_pdf")

# ------------------------------------------------------------------ 1. Cargar archivos
elif pagina == "cargar":
    pasos(1)
    mostrar_avisos()
    st.header("¿Qué archivos quieres agregar?")
    st.caption("Excel o CSV con listas de atenciones o participaciones, o formularios en PDF o foto (una atención por página).")
    with st.container(key="zona_subida"):
        subidos = st.file_uploader("Archivos", type=["xlsx", "csv", "pdf", "png", "jpg", "jpeg"], accept_multiple_files=True,
                                   key=f"subida_{ss.subida}", label_visibility="collapsed")
    if subidos:
        for archivo in subidos:
            nuevo_lote(archivo.name, archivo.getvalue())
        ss.subida += 1
        st.rerun()
    ej = st.container(horizontal=True, vertical_alignment="center")
    ej.caption("¿Quieres probar? Usa un ejemplo:")
    for etq, archivos, icono, key in [
        ("Atenciones y participaciones", ("atenciones.xlsx", "participaciones.xlsx"), ":material/table_chart:", "ej_bases"),
        ("Formato escaneado (PDF)", ("citologia_escaneo.pdf",), ":material/picture_as_pdf:", "ej_pdf"),
        ("Formato en fotos", ("mamaria_foto.png", "mamaria_foto_pagina2.png"), ":material/photo_camera:", "ej_png"),
        ("Excel de jornada", ("ejemplo_atenciones_nuevas.xlsx",), ":material/grid_on:", "ej_excel"),
        ("Formato en blanco", ("formato_en_blanco_escaneo.pdf",), ":material/draft:", "ej_blanco")]:
        ej.button(etq, icon=icono, on_click=cargar_ejemplo, args=archivos, key=key)

    for lote in list(ss.lotes.values()):
        with st.container(border=True):
            fila = st.columns([8, 1], vertical_alignment="center")
            fila[1].button("Quitar", icon=":material/delete:", key=f"quitar_{lote['id']}", on_click=quitar_lote, args=(lote["id"],))
            if lote["tipo"] in ("excel", "csv"):
                falta = faltantes(lote)
                if lote["registros"] is not None and not falta:
                    fila[0].markdown(f":green[:material/check_circle:] **Reconocimos {lote['archivo']}:** {resumen_tipos(lote['registros'])}")
                elif lote["registros"] is not None:
                    fila[0].markdown(f":orange[:material/help:] **{lote['archivo']}:** {resumen_tipos(lote['registros'])}. "
                                     f"No encontramos la columna de: {', '.join(NOMBRES_CAMPO[c].split(' (')[0].lower() for c in falta)}. "
                                     "Si existe, elígela en «Ajustar columnas».")
                else:
                    fila[0].markdown(f":red[:material/error:] **{lote['archivo']}:** no encontramos la columna del folio. "
                                     "Elígela en «Ajustar columnas» para continuar.")
                with st.expander("Ajustar columnas (avanzado)", expanded=lote["registros"] is None, icon=":material/tune:"):
                    hojas = list(lote["hojas"])
                    if len(hojas) > 1:
                        lote["hoja"] = st.selectbox("Hoja", hojas, index=hojas.index(lote["hoja"]), key=f"hoja_{lote['id']}")
                    frame = lote["hojas"][lote["hoja"]]
                    st.dataframe(frame.head(5).astype(str), hide_index=True, alt="Primeras filas del archivo")
                    cols = [str(c) for c in frame.columns]
                    opciones = [SIN_ASIGNAR] + cols
                    tipo = st.selectbox("Este archivo contiene", TIPOS_EVENTO, index=TIPOS_EVENTO.index(lote["tipo_defecto"]),
                                        key=f"tipo_{lote['id']}")
                    dos = st.toggle("El nombre viene en dos columnas (nombres y apellidos)", value=bool(lote["mapeo"].get("nombres")),
                                    key=f"dos_{lote['id']}")
                    campos = ["folio", "fecha", "programa", "municipio"] + (["nombres", "apellidos"] if dos else ["nombre"]) + \
                             ["edad", "servicio", "padecimiento", "tipo_evento"]
                    nuevo, grid = {}, st.columns(3)
                    for j, c in enumerate(campos):
                        actual = lote["mapeo"].get(c)
                        sel = grid[j % 3].selectbox(NOMBRES_CAMPO[c] if c != "tipo_evento" else "Tipo de registro por fila", opciones,
                                                    index=opciones.index(actual) if actual in opciones else 0,
                                                    key=f"map_{lote['id']}_{lote['hoja']}_{c}")
                        nuevo[c] = None if sel == SIN_ASIGNAR else sel
                    if st.button("Usar estas columnas", key=f"aplicar_{lote['id']}", icon=":material/check:"):
                        lote["mapeo"], lote["tipo_defecto"] = nuevo, tipo
                        aplicar_lote(lote)
                        st.rerun()
            else:
                doc = lote["doc"]
                c1, c2 = fila[0].columns([1, 4], vertical_alignment="center")
                if doc.get("imagen") is not None:
                    c1.image(doc["imagen"], width=110, alt=f"Miniatura de {lote['archivo']}")
                r = lote["registros"][0]
                lectura = {"texto PDF": "texto del PDF", "OCR": "lectura de imagen", "OCR (PDF escaneado)": "lectura de PDF escaneado"}.get(doc["metodo"], doc["metodo"])
                if doc.get("error"):
                    c2.markdown(f":red[:material/error:] **{lote['archivo']}:** {doc['error']}  \n"
                                "Podrás escribir los datos a mano en el siguiente paso.")
                elif doc["sin_datos"]:
                    c2.markdown(f":orange[:material/help:] **{lote['archivo']}: sin datos suficientes.** Parece un formato en blanco o ilegible. "
                                "Podrás escribir los datos a mano en el siguiente paso.")
                else:
                    c2.markdown(f":green[:material/check_circle:] **Leímos {lote['archivo']}** ({lectura}): "
                                f"{r.get('folio') or 'sin folio'} · {r.get('nombre') or 'sin nombre'}")
                if doc.get("formulario"):
                    c2.caption(f"{doc['formulario']['titulo']} · {doc['paginas']} página(s) leída(s) campo por campo.")
                elif doc.get("paginas", 1) > 1:
                    c2.caption(f"Tiene {doc['paginas']} páginas; solo se lee la primera.")

    nav = st.container(horizontal=True, horizontal_alignment="distribute")
    nav.button("Volver al tablero", icon=":material/arrow_back:", on_click=ir, args=("tablero",), key="atras_1")
    nav.button("Siguiente: revisar datos", icon=":material/arrow_forward:", type="primary", disabled=not lotes_listos(),
               on_click=ir, args=("revisar",), key="sig_revisar")

# ------------------------------------------------------------------ 2. Revisar datos
elif pagina == "revisar":
    pasos(2)
    listos = lotes_listos()
    if not listos:
        st.info("No hay archivos para revisar.", icon=":material/info:")
    total = sum(len(l["registros"]) for l in listos)
    tarjetas = [(l, i, r) for l in listos for i, r in enumerate(l["registros"])
                if l["tipo"] in ("pdf", "imagen") or problemas(r)]
    conflictos = sum(e.startswith("Folio existente") for l in listos for e in db.clasificar(conn, l["registros"]))
    st.header("Revisa solo lo que necesita tu atención")
    if tarjetas:
        st.markdown(f"De **{total}** registros, **{total - len(tarjetas)}** están listos :green[:material/check_circle:] y "
                    f"**{len(tarjetas)}** necesitan tu atención.")
    else:
        st.success(f"Los {total} registros están listos. No encontramos nada que corregir.", icon=":material/check_circle:")
    if conflictos:
        st.info(f"{conflictos} folio(s) ya estaban guardados con otros datos. No los sobrescribiremos: después de guardar podrás "
                "decidir cuál versión conservar.", icon=":material/info:")

    for n, (lote, i, r) in enumerate(tarjetas):
        if n == MAX_TARJETAS and not st.toggle(f"Mostrar las {len(tarjetas) - MAX_TARJETAS} restantes", key="mas_tarjetas"):
            break
        with st.container(border=True):
            titulo = f"**{r.get('folio') or 'Sin folio'} · {r.get('nombre') or 'Sin nombre'}**"
            origen = f"{lote['archivo']} · {r['ubicacion']}"
            if lote["tipo"] in ("pdf", "imagen"):
                doc = lote["doc"]
                st.markdown(f":material/description: {titulo}")
                st.caption(f"{origen} · revisa que los datos coincidan con el documento")
                izq, der = st.columns([1, 1])
                for n, im in enumerate(doc.get("imagenes") or ([doc["imagen"]] if doc.get("imagen") is not None else [])):
                    izq.image(im, alt=f"Documento {lote['archivo']}, página {n + 1}")
                dudosos = (doc.get("formulario") or {}).get("dudosos") or []
                if dudosos:
                    der.warning("Lectura dudosa, compárala con la imagen: " + ", ".join(dudosos) + ".", icon=":material/visibility:")
                if doc.get("error"):
                    der.error(doc["error"], icon=":material/error:")
                if doc["sin_datos"]:
                    der.warning("Sin datos suficientes. Escribe al menos el folio y el nombre para poder guardarlo.", icon=":material/edit_note:")
                for campo in EDITABLES:
                    estado = campo_editable(lote, i, r, campo, der)
                    icono = {"Extraído automáticamente": ":green[:material/auto_awesome:]", "Corregido en revisión": ":blue[:material/edit:]",
                             "Captura manual": ":blue[:material/keyboard:]", "Sin dato": ":gray[:material/remove:]"}[estado]
                    der.caption(f"{icono} {estado}" + (f" · se mostrará «{NO_REGISTRADO}»" if campo == "padecimiento" and estado == "Sin dato" else ""))
                if not (r.get("folio") and r.get("nombre")):
                    der.error("Faltan el folio o el nombre: este documento no se guardará.", icon=":material/block:")
            else:
                st.markdown(f":orange[:material/warning:] {titulo}")
                st.caption(origen)
                vistos = []
                for campo, msg in problemas(r):
                    st.markdown(msg)
                    if campo not in vistos:
                        campo_editable(lote, i, r, campo)
                        vistos.append(campo)
                pendientes = problemas(r) if all(r["_prop"][c] == vista(r, c) for c in vistos) else []
                st.caption(":blue[:material/edit:] Corregido" if not pendientes and vistos else
                           "Si no lo corriges, se guardará tal como está.")
                with st.expander("Ver o corregir otros datos de este registro"):
                    for campo in EDITABLES:
                        if campo not in vistos:
                            campo_editable(lote, i, r, campo)
                    st.caption("Valores originales: " + "; ".join(f"{k}={v}" for k, v in r.get("originales", {}).items() if v))

    with st.expander("Buscar y corregir cualquier registro (avanzado)", icon=":material/manage_search:"):
        en_tarjeta = {(l["id"], i) for l, i, _ in tarjetas}
        tabulares = [(l, i, r) for l in listos if l["tipo"] in ("excel", "csv") for i, r in enumerate(l["registros"])
                     if (l["id"], i) not in en_tarjeta]
        st.caption("Los registros con avisos ya aparecen arriba.")
        if tabulares:
            etiquetas = [f"{r.get('folio') or 'sin folio'} · {r.get('nombre') or ''} ({l['archivo']})" for l, i, r in tabulares]
            elegido = st.selectbox("Registro", range(len(tabulares)), format_func=lambda j: etiquetas[j], key="buscar_registro",
                                   index=None, placeholder="Escribe un folio o un nombre")
            if elegido is not None:
                l, i, r = tabulares[elegido]
                st.caption(f"{l['archivo']} · {r['ubicacion']}")
                cols = st.columns(3)
                for j, campo in enumerate(EDITABLES):
                    campo_editable(l, i, r, campo, cols[j % 3])

    nav = st.container(horizontal=True, horizontal_alignment="distribute")
    nav.button("Atrás", icon=":material/arrow_back:", on_click=ir, args=("cargar",), key="atras_2")
    nav.button("Siguiente: confirmar", icon=":material/arrow_forward:", type="primary", disabled=not listos,
               on_click=ir, args=("confirmar",), key="sig_confirmar")

# ------------------------------------------------------------------ 3. Confirmar
elif pagina == "confirmar":
    pasos(3)
    st.header("Confirma antes de guardar")
    listos = lotes_listos()
    finales = {l["id"]: registros_finales(l) for l in listos}
    cuenta = {"Nuevos": 0, "Ya guardados": 0, "Datos distintos": 0, "No se guardarán": 0}
    for regs, _ in finales.values():
        for e in db.clasificar(conn, regs):
            if e == "Nuevo":
                cuenta["Nuevos"] += 1
            elif e.startswith("Folio existente"):
                cuenta["Datos distintos"] += 1
            elif e.startswith("Sin folio"):
                cuenta["No se guardarán"] += 1
            else:
                cuenta["Ya guardados"] += 1
    cambios = [c for _, cs in finales.values() for c in cs]
    m = st.columns(4)
    m[0].metric("Actividades nuevas", cuenta["Nuevos"], border=True, icon=":material/add_circle:")
    m[1].metric("Ya estaban guardadas", cuenta["Ya guardados"], border=True, icon=":material/done_all:",
                help="Mismo folio y mismos datos: no se duplican.")
    m[2].metric("Folios con datos distintos", cuenta["Datos distintos"], border=True, icon=":material/difference:",
                help="No se sobrescriben. Podrás decidir después de guardar.")
    m[3].metric("Correcciones", len(cambios), border=True, icon=":material/edit:")
    if cuenta["No se guardarán"]:
        st.warning(f"{cuenta['No se guardarán']} registro(s) no tienen folio (o, en documentos, folio y nombre) y no se guardarán.",
                   icon=":material/block:")
    if cambios:
        with st.expander(f"Ver las {len(cambios)} correcciones que quedarán en la bitácora"):
            st.dataframe(pd.DataFrame(cambios, columns=["Folio", "Campo", "Antes", "Después", "Origen"]), hide_index=True,
                         alt="Correcciones por registrar")
    st.caption("Al guardar se registran la fecha y la hora de confirmación y el archivo y fila de origen de cada dato.")

    def guardar():
        for lid, (regs, cs) in finales.items():
            lote = ss.lotes[lid]
            res = db.confirmar(conn, regs, cs, lote["archivo"], lote["sha"], lote["tipo"])
            texto_res = f"{lote['archivo']}: {res['nuevos']} nuevas, {res['sin_cambios']} ya estaban guardadas"
            if res["conflictos"]:
                texto_res += f", {res['conflictos']} con datos distintos para revisar"
            ss.flash.append(("success", texto_res + "."))
            del ss.lotes[lid]
        ss.pagina = "tablero"

    nav = st.container(horizontal=True, horizontal_alignment="distribute")
    nav.button("Atrás", icon=":material/arrow_back:", on_click=ir, args=("revisar",), key="atras_3")
    nav.button("Guardar", icon=":material/save:", type="primary", on_click=guardar, key="guardar", disabled=not finales)

# ------------------------------------------------------------------ Pendientes (conflictos y coincidencias)
elif pagina == "pendientes":
    st.button("Volver al tablero", icon=":material/arrow_back:", on_click=ir, args=("tablero",), key="atras_p")
    st.title("Revisión de pendientes")
    mostrar_avisos()

    conf = db.conflictos_df(conn)
    if len(conf):
        st.header(f"Folios que llegaron con datos distintos ({len(conf)})")
        for _, c in conf.iterrows():
            act, ent = db.extra(c["datos_actuales_json"]), db.extra(c["datos_entrantes_json"])
            dif = {NOMBRES_CAMPO.get(k, k).split(" (")[0]: (act.get(k), ent.get(k)) for k in act if act.get(k) != ent.get(k)}
            with st.container(border=True):
                st.markdown(f"**El folio {c['folio']} ya estaba guardado** y llegó otra vez desde {c['archivo']} ({c['ubicacion']}) con datos distintos.")
                st.table(pd.DataFrame({"Lo que ya estaba guardado": [v[0] for v in dif.values()],
                                       "Lo que llegó": [v[1] for v in dif.values()]}, index=list(dif)).astype(str))
                b = st.container(horizontal=True)
                b.button("Conservar lo guardado", key=f"mant_{c['id']}", on_click=resolver, args=(int(c["id"]), False), icon=":material/shield:")
                b.button("Usar lo que llegó", key=f"apl_{c['id']}", on_click=resolver, args=(int(c["id"]), True), icon=":material/sync:")

    sug = db.sugerencias_df(conn)
    st.header("¿Son la misma persona?")
    st.caption("EIRA no tiene un número único por paciente. Sugerimos parejas de registros con nombres que se escriben igual o "
               "muy parecido. Solo tu decisión los une; el folio identifica una actividad, no a una persona.")
    if not len(sug):
        st.info("No hay sugerencias por ahora.", icon=":material/info:")
    else:
        filtros_p = {"Todas": None, "Casos claros": PRIORIDAD_ALTA, "Escritura parecida": PRIORIDAD_REVISAR,
                     "Mismo nombre, otra edad o municipio": PRIORIDAD_HOMONIMAS}
        ver = st.segmented_control("Mostrar", list(filtros_p), default="Todas", required=True, key="filtro_pend")
        pendientes = sug[sug["estado"] == db.PENDIENTE]
        if filtros_p[ver]:
            pendientes = pendientes[pendientes["prioridad"] == filtros_p[ver]]
        por_ver = pendientes[[(a, b) not in ss.saltadas for a, b in zip(pendientes["folio_a"], pendientes["folio_b"])]]
        hechas = int((sug["estado"] != db.PENDIENTE).sum())
        st.progress(hechas / len(sug), text=f"Has revisado {hechas} de {len(sug)} posibles coincidencias")

        if len(por_ver):
            s = por_ver.iloc[0]
            acts = db.actividades_df(conn).set_index("folio")
            st.subheader(f"Coincidencia 1 de {len(por_ver)}" + ("" if ver == "Todas" else f" · {ver.lower()}"))
            fichas = st.columns(2)
            for col, lado in zip(fichas, ("a", "b")):
                folio = s[f"folio_{lado}"]
                a = acts.loc[folio]
                with col.container(border=True, height="stretch"):
                    st.markdown(f"### {tx(s[f'original_{lado}'], tx(s[f'nombre_{lado}']))}")
                    st.markdown(f":material/cake: **Edad:** {'sin dato' if pd.isna(a['edad']) else int(a['edad'])}  \n"
                                f":material/location_on: **Municipio:** {tx(a['municipio'], SIN_MUNICIPIO)}  \n"
                                f":material/event_note: **Actividad:** {a['tipo_evento']} · {tx(a['servicio'])} · "
                                f"{fecha_vista(dict(a)) or 'sin fecha'}  \n"
                                f":material/folder: **De dónde viene:** {a['archivo_origen']}, {a['ubicacion_origen']} (folio {folio})")
            motivo = s["motivo"][0].upper() + s["motivo"][1:]
            st.markdown(f"**¿Por qué la sugerimos?** {motivo}.")
            if s["prioridad"] == PRIORIDAD_HOMONIMAS:
                st.warning("Tienen el mismo nombre, pero otra edad o municipio: podrían ser dos personas distintas.", icon=":material/warning:")
            b = st.container(horizontal=True)
            b.button("Es la misma persona", type="primary", icon=":material/link:", key="pend_misma",
                     on_click=decidir, args=(s["folio_a"], s["folio_b"], db.VINCULAR))
            b.button("Son personas distintas", icon=":material/link_off:", key="pend_distintas",
                     on_click=decidir, args=(s["folio_a"], s["folio_b"], db.DISTINTAS))
            b.button("Decidir después", icon=":material/schedule:", key="pend_despues", on_click=saltar, args=(s["folio_a"], s["folio_b"]))
        elif len(pendientes):
            st.info(f"Dejaste {len(pendientes)} para después.", icon=":material/schedule:")
            st.button("Volver a verlas", on_click=lambda: setattr(ss, "saltadas", set()), key="ver_saltadas")
        else:
            st.success("¡Listo! No quedan coincidencias por revisar en esta vista.", icon=":material/check_circle:")

        claros = sug[(sug["estado"] == db.PENDIENTE) & (sug["prioridad"] == PRIORIDAD_ALTA)]
        if len(claros):
            with st.expander(f"Revisar en bloque los casos claros ({len(claros)})", icon=":material/playlist_add_check:"):
                st.caption("Parejas con el mismo nombre, la misma edad y el mismo municipio. Revisa la lista antes de confirmar.")
                st.dataframe(pd.DataFrame({"Nombre A": claros["original_a"].fillna(claros["nombre_a"]), "Folio A": claros["folio_a"],
                                           "Nombre B": claros["original_b"].fillna(claros["nombre_b"]), "Folio B": claros["folio_b"],
                                           "Edad": claros["edad_a"], "Municipio": claros["municipio_a"]}),
                             hide_index=True, alt="Casos claros de posible misma persona")
                revisado = st.checkbox("Revisé la lista y todas son la misma persona", key="ok_bloque")
                if st.button(f"Marcar las {len(claros)} como la misma persona", disabled=not revisado, key="bloque", type="primary"):
                    n = db.guardar_decisiones(conn, [(a, b, db.VINCULAR) for a, b in zip(claros["folio_a"], claros["folio_b"])])
                    ss.flash.append(("success", f"Se registraron {n} decisiones en la bitácora."))
                    st.rerun()

        decididas = sug[sug["estado"] != db.PENDIENTE]
        if len(decididas):
            with st.expander(f"Decisiones tomadas ({len(decididas)}) · cambiar una decisión", icon=":material/history:"):
                tabla = pd.DataFrame({"Decisión": decididas["estado"], "Nombre A": decididas["original_a"].fillna(decididas["nombre_a"]),
                                      "Folio A": decididas["folio_a"], "Nombre B": decididas["original_b"].fillna(decididas["nombre_b"]),
                                      "Folio B": decididas["folio_b"]})
                ed = st.data_editor(tabla, hide_index=True, disabled=["Nombre A", "Folio A", "Nombre B", "Folio B"], key=f"dec_{len(decididas)}",
                                    column_config={"Decisión": st.column_config.SelectboxColumn(options=db.DECISIONES, required=True)},
                                    alt="Decisiones de identidad")
                if st.button("Guardar cambios", key="guardar_dec"):
                    db.guardar_decisiones(conn, list(zip(ed["Folio A"], ed["Folio B"], ed["Decisión"])))
                    st.rerun()

# ------------------------------------------------------------------ Buscar beneficiaria
elif pagina == "buscar":
    st.button("Volver al tablero", icon=":material/arrow_back:", on_click=ir, args=("tablero",), key="atras_b")
    st.title("Buscar beneficiaria")
    st.caption(":material/lock: Vista reservada: muestra nombres y datos de salud. No se incluye en el informe.")
    base = report.preparar(db.actividades_df(conn))
    if not len(base):
        st.info("Aún no hay datos guardados.", icon=":material/info:")
        st.stop()
    opciones = base.sort_values(["nombre", "folio"])
    nombres = {f: tx(n, "(sin nombre)") for f, n in zip(opciones["folio"], opciones["nombre"])}
    elegido = st.selectbox("Escribe un nombre o un folio", list(nombres), index=None, placeholder="Por ejemplo: Ana García",
                           format_func=lambda f: f"{nombres[f]} · {f}", key="buscar_f")
    if elegido:
        personas = db.mapa_personas(conn)
        grupo = [f for f, rep in personas.items() if rep == personas[elegido]]
        acts = base[base["folio"].isin(grupo)].sort_values("fecha", na_position="last")
        p = acts[acts["folio"] == elegido].iloc[0]
        st.header(tx(p["nombre"], "(sin nombre)"))
        m = st.columns(3)
        m[0].metric("Actividades", len(acts), border=True, icon=":material/event_note:",
                    help="Solo se suman actividades unidas por una persona en la revisión de coincidencias.")
        m[1].metric("Edad", "" if pd.isna(p["edad"]) else int(p["edad"]), border=True, icon=":material/cake:",
                    help=f"Según {p['archivo_origen']}, {p['ubicacion_origen']}")
        m[2].metric("Municipio", p["municipio_vista"], border=True, icon=":material/location_on:",
                    help=f"Según {p['archivo_origen']}, {p['ubicacion_origen']}")
        if len(grupo) == 1:
            st.caption("No hay otras actividades unidas a esta persona por revisión humana.")
        st.subheader("Fechas de atención y actividades")
        st.dataframe(pd.DataFrame({
            "Fecha": [fecha_vista(dict(r)) + ("" if r["fecha_valida"] else " (fecha inválida)") for _, r in acts.iterrows()],
            "Tipo": acts["tipo_evento"], "Servicio o actividad": acts["servicio"], "Programa": acts["programa"],
            "Padecimiento": acts["padecimiento"].fillna(NO_REGISTRADO), "Edad": acts["edad"], "Municipio": acts["municipio_vista"],
            "Fuente": acts["archivo_origen"] + ", " + acts["ubicacion_origen"], "Folio": acts["folio"]}).astype(str),
            hide_index=True, alt="Actividades de la beneficiaria")
        citas = acts[acts["tipo_evento"] == CITA]
        if len(citas):
            st.markdown("**Citas agendadas (según la fuente):** " + ", ".join(f"{fecha_vista(dict(r))} · {r['servicio']}" for _, r in citas.iterrows()))
        else:
            st.caption("La fuente no identifica citas agendadas para esta persona.")
        s = db.sugerencias_df(conn)
        rel = s[(s["folio_a"].isin(grupo) | s["folio_b"].isin(grupo)) & (s["estado"] == db.PENDIENTE)]
        if len(rel):
            st.info(f"Hay {len(rel)} posible(s) coincidencia(s) sin revisar para esta persona.", icon=":material/pending_actions:")
            st.button("Revisarlas", on_click=ir, args=("pendientes",), key="buscar_pend")
