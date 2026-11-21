import hashlib
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from eira import config, db, report
from eira.config import (CITA, DATOS, EJEMPLOS, ETIQUETAS, NO_REGISTRADO, SIN_DATOS, SIN_MUNICIPIO, TIPOS_EVENTO)
from eira.matching import mejor_coincidencia
from eira.quality import banderas, normalizar_municipio, original, parse_edad, parse_fecha, texto
from eira.tabular import aplicar_mapeo, inferir_tipo_evento, leer_tabla, proponer_mapeo

st.set_page_config(page_title="EIRA · Impacto social", page_icon="🎗️", layout="wide")

SIN_ASIGNAR = "(sin asignar)"
EDITABLES = ["folio", "fecha", "tipo_evento", "programa", "municipio", "nombre", "edad", "servicio", "padecimiento"]
TABULARES = (".xlsx", ".csv")
DOCUMENTOS = (".pdf", ".png", ".jpg", ".jpeg")

ss = st.session_state
ss.setdefault("lotes", {})
ss.setdefault("contador", 0)
ss.setdefault("uploader", 0)
ss.setdefault("flash", [])


@st.cache_resource
def conexion(ruta: str):
    return db.conectar(ruta)


conn = conexion(str(config.DB_PATH))


# ---------------------------------------------------------------- utilidades
def nuevo_lote(nombre: str, contenido: bytes):
    sha = hashlib.sha256(contenido).hexdigest()
    if any(l["sha"] == sha for l in ss.lotes.values()):
        ss.flash.append(("warning", f"«{nombre}» ya está en la lista de carga."))
        return
    ss.contador += 1
    lote = {"id": ss.contador, "archivo": nombre, "sha": sha, "contenido": contenido, "registros": None}
    low = nombre.lower()
    try:
        if low.endswith(TABULARES):
            lote["tipo"] = "csv" if low.endswith(".csv") else "excel"
            lote["hojas"] = leer_tabla(nombre, contenido)
        elif low.endswith(DOCUMENTOS):
            from eira import documents
            lote["tipo"] = "pdf" if low.endswith(".pdf") else "imagen"
            lote["doc"] = documents.procesar(nombre, contenido)
        else:
            ss.flash.append(("error", f"Formato no soportado: {nombre}"))
            return
    except Exception as e:  # archivo dañado o ilegible
        ss.flash.append(("error", f"No se pudo leer «{nombre}»: {e}"))
        return
    ss.lotes[lote["id"]] = lote


def fecha_vista(r) -> str:
    if r.get("fecha_valida") and r.get("fecha"):
        return date.fromisoformat(r["fecha"]).strftime("%d/%m/%Y")
    return r.get("fecha_original") or ""


def vista(r, campo) -> str:
    if campo == "fecha":
        return fecha_vista(r)
    v = r.get(campo)
    return "" if v is None else str(v)


def aplicar_valor(r: dict, campo: str, valor: str):
    valor = texto(valor)
    if campo == "fecha":
        r["fecha"], r["fecha_valida"] = parse_fecha(valor)
        if not r.get("fecha_original"):
            r["fecha_original"] = valor
        elif not r["fecha_valida"]:
            r["fecha_original"] = valor
    elif campo == "edad":
        r["edad"] = parse_edad(valor)
    elif campo == "municipio":
        r["municipio"] = normalizar_municipio(valor)[0]
    elif campo == "folio":
        r["folio"] = valor.upper()
    else:
        r[campo] = valor or None


def candidatos_nombre(excluir_lote=None):
    c = [(r["folio"], r["nombre"]) for r in conn.execute("SELECT folio, nombre FROM actividades")]
    for l in ss.lotes.values():
        if l["id"] != excluir_lote and l.get("registros"):
            c += [(r["folio"], r.get("nombre")) for r in l["registros"]]
    return c


def resumen_originales(r) -> str:
    return "; ".join(f"{k}={v}" for k, v in r.get("originales", {}).items() if v)


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.title("EIRA · Movimiento Rosa")
    st.caption("Reto 3 · Consolidación y visualización del impacto social (prototipo local con datos ficticios)")
    n_act = conn.execute("SELECT COUNT(*) FROM actividades").fetchone()[0]
    st.metric("Actividades guardadas", n_act)
    st.metric("Archivos en carga", len(ss.lotes))
    st.metric("Identidades pendientes", db.identidades_pendientes(conn))
    st.metric("Conflictos de folio", len(db.conflictos_df(conn)))
    st.divider()
    with st.expander("Reiniciar demo"):
        st.write("Borra todas las actividades, decisiones y la bitácora de la base local.")
        ok = st.checkbox("Entiendo que se borrarán todos los datos guardados")
        if st.button("Reiniciar demo", type="primary", disabled=not ok):
            db.reiniciar(conn)
            for k in list(ss.keys()):
                del ss[k]
            st.rerun()

for nivel, msg in ss.flash:
    getattr(st, nivel)(msg)
ss.flash = []

st.title("Consolidación del impacto social")
paso1, paso2, paso3, paso4 = st.tabs(["1. Cargar archivos", "2. Revisar datos", "3. Confirmar", "4. Ver tablero"])

# ---------------------------------------------------------------- 1. Cargar
with paso1:
    st.subheader("Paso 1 · Cargar archivos")
    st.write("Acepta Excel (.xlsx), CSV, PDF y PNG (también JPG). Los documentos se acotan a un formulario de una página por atención.")
    b = st.columns(5)
    if b[0].button("Cargar datos de ejemplo", type="primary", help="Datos/atenciones.xlsx y Datos/participaciones.xlsx"):
        for p in (DATOS / "atenciones.xlsx", DATOS / "participaciones.xlsx"):
            nuevo_lote(p.name, p.read_bytes())
        st.rerun()
    ejemplos = [("Ejemplo PDF", "ejemplo_formulario.pdf"), ("Ejemplo PNG", "ejemplo_formulario.png"),
                ("Ejemplo Excel", "ejemplo_atenciones_nuevas.xlsx"), ("Formato en blanco", "formato_en_blanco.pdf")]
    for col, (etq, arch) in zip(b[1:], ejemplos):
        p = EJEMPLOS / arch
        if col.button(etq, disabled=not p.exists(), help=f"Datos/ejemplos/{arch}"):
            nuevo_lote(p.name, p.read_bytes())
            st.rerun()

    subidos = st.file_uploader("Subir archivos", type=["xlsx", "csv", "pdf", "png", "jpg", "jpeg"],
                               accept_multiple_files=True, key=f"up_{ss.uploader}")
    if subidos:
        for f in subidos:
            nuevo_lote(f.name, f.getvalue())
        ss.uploader += 1
        st.rerun()

    if not ss.lotes:
        st.info("Todavía no hay archivos en carga.")
    for lote in list(ss.lotes.values()):
        with st.expander(f"📄 {lote['archivo']}", expanded=True):
            top = st.columns([6, 1])
            if top[1].button("Quitar", key=f"quitar_{lote['id']}"):
                del ss.lotes[lote["id"]]
                st.rerun()
            if lote["tipo"] in ("excel", "csv"):
                hojas = list(lote["hojas"])
                if not hojas:
                    st.error("El archivo no contiene filas.")
                    continue
                hoja = top[0].selectbox("Hoja", hojas, key=f"hoja_{lote['id']}") if len(hojas) > 1 else hojas[0]
                frame = lote["hojas"][hoja]
                st.caption(f"Vista previa: {len(frame)} filas · columnas detectadas: {', '.join(map(str, frame.columns))}")
                st.dataframe(frame.head(10).astype(str), width="stretch", hide_index=True)
                cols = [str(c) for c in frame.columns]
                propuesta = proponer_mapeo(cols)
                st.markdown("**Confirma qué columna corresponde a cada campo**")
                mc = st.columns(3)
                tipo_def = mc[0].selectbox("Tipo de evento del archivo", TIPOS_EVENTO,
                                           index=TIPOS_EVENTO.index(inferir_tipo_evento(cols, lote["archivo"])),
                                           key=f"tipo_{lote['id']}")
                usa_dos = bool(propuesta.get("nombres"))
                modo = mc[1].radio("Nombre", ["Una columna", "Nombres + apellidos"], index=int(usa_dos),
                                   key=f"modo_{lote['id']}", horizontal=True)
                opciones = [SIN_ASIGNAR] + cols
                campos = ["folio", "fecha", "programa", "municipio"]
                campos += ["nombres", "apellidos"] if modo == "Nombres + apellidos" else ["nombre"]
                campos += ["edad", "servicio", "padecimiento", "tipo_evento"]
                etq = {**ETIQUETAS, "nombres": "Nombre(s)", "apellidos": "Apellidos",
                       "tipo_evento": "Tipo de evento por fila (opcional)"}
                mapeo = {}
                grid = st.columns(4)
                for i, campo in enumerate(campos):
                    prop = propuesta.get(campo)
                    sel = grid[i % 4].selectbox(etq[campo], opciones, index=opciones.index(prop) if prop in opciones else 0,
                                                key=f"map_{lote['id']}_{hoja}_{campo}")
                    mapeo[campo] = None if sel == SIN_ASIGNAR else sel
                sin_map = [c for c in cols if c not in mapeo.values()]
                if sin_map:
                    st.caption("Columnas no usadas (se conservan como valor original): " + ", ".join(sin_map))
                actual = {"hoja": hoja, "mapeo": mapeo, "tipo": tipo_def}
                if not mapeo.get("folio"):
                    st.warning("Asigna la columna del folio: identifica cada actividad.")
                if st.button("Confirmar mapeo y pasar a revisión", key=f"aplicar_{lote['id']}", disabled=not mapeo.get("folio")):
                    lote["mapeo_confirmado"] = actual
                    lote["registros"] = aplicar_mapeo(frame, mapeo, tipo_def, lote["archivo"], hoja)
                    st.rerun()
                if lote.get("registros") is not None:
                    if lote.get("mapeo_confirmado") != actual:
                        st.warning("Cambiaste el mapeo: vuelve a confirmarlo para actualizar la revisión.")
                    else:
                        st.success(f"{len(lote['registros'])} registros listos en «2. Revisar datos».")
            else:
                doc = lote["doc"]
                izq, der = st.columns([1, 1])
                if doc.get("imagen") is not None:
                    izq.image(doc["imagen"], caption=f"{lote['archivo']} · página 1", width="stretch")
                if doc.get("paginas", 1) > 1:
                    der.warning(f"El documento tiene {doc['paginas']} páginas; la demo procesa solo la página 1.")
                if doc.get("error"):
                    der.error(doc["error"])
                    der.info("Puedes capturar los datos manualmente en «2. Revisar datos». Quedarán marcados como captura manual.")
                der.markdown(f"**Método de lectura:** {doc['metodo']}")
                if doc["sin_datos"]:
                    der.warning(f"{SIN_DATOS}: el documento parece un formato en blanco o ilegible.")
                der.dataframe(pd.DataFrame([{"Campo": ETIQUETAS[c], "Valor extraído": doc["campos"].get(c) or "—",
                                             "Estado": "Extraído automáticamente" if doc["campos"].get(c) else "No encontrado"}
                                            for c in EDITABLES]), hide_index=True, width="stretch")
                with der.expander("Texto leído del documento"):
                    st.text(doc.get("texto") or "(sin texto)")
                if lote.get("registros") is None:
                    from eira import documents
                    lote["registros"] = [documents.a_registro(doc, lote["archivo"])]
                    st.rerun()

# ---------------------------------------------------------------- 2. Revisar
editados: dict[int, tuple[list[dict], list[tuple]]] = {}
with paso2:
    st.subheader("Paso 2 · Revisar datos")
    listos = [l for l in ss.lotes.values() if l.get("registros") is not None]
    if not listos:
        st.info("Confirma el mapeo de algún archivo en «1. Cargar archivos» para revisarlo aquí.")
    for lote in listos:
        regs = lote["registros"]
        st.markdown(f"### {lote['archivo']}")
        if lote["tipo"] in ("excel", "csv"):
            estados = db.clasificar(conn, regs)
            cand = candidatos_nombre(lote["id"])
            filas = []
            for r, est in zip(regs, estados):
                m = mejor_coincidencia(r.get("nombre"), cand + [(x["folio"], x.get("nombre")) for x in regs if x is not r], excluir=r["folio"])
                filas.append({**{ETIQUETAS[c] if c != "padecimiento" else "Padecimiento": vista(r, c) for c in EDITABLES},
                              "Alertas": ", ".join(banderas(r) + r.get("notas", [])),
                              "Estado al guardar": est,
                              "Posible coincidencia": f"{m[0]} ({m[1]:.0f} %)" if m else "",
                              "Procedencia": f"{r['archivo']}, {r['ubicacion']}",
                              "Valor original": resumen_originales(r)})
            tabla = pd.DataFrame(filas)
            n_alert = (tabla["Alertas"] != "").sum()
            c = st.columns(4)
            c[0].metric("Registros", len(tabla))
            c[1].metric("Con alertas", int(n_alert))
            c[2].metric("Folio existente con datos diferentes", int(tabla["Estado al guardar"].str.startswith("Folio existente").sum()))
            c[3].metric("Con posible coincidencia", int((tabla["Posible coincidencia"] != "").sum()))
            solo = st.toggle("Mostrar solo filas con alertas o conflictos", key=f"solo_{lote['id']}")
            st.caption("Corrige directamente en la tabla. El padecimiento vacío se mostrará como «No registrado». "
                       "Las columnas grises son de solo lectura: conservan el valor original y su procedencia.")
            bloqueadas = ["Alertas", "Estado al guardar", "Posible coincidencia", "Procedencia", "Valor original"]
            idx = tabla.index[(tabla["Alertas"] != "") | ~tabla["Estado al guardar"].isin(["Nuevo", "Sin cambios (ya guardado)"])] if solo else tabla.index
            edit = st.data_editor(
                tabla.loc[idx], key=f"ed_{lote['id']}_{solo}", hide_index=True, width="stretch", num_rows="fixed",
                disabled=bloqueadas,
                column_config={ETIQUETAS["tipo_evento"]: st.column_config.SelectboxColumn(options=TIPOS_EVENTO, required=True),
                               "Padecimiento": st.column_config.TextColumn(help="Transcribe solo si la fuente lo registra explícitamente")})
            nuevos, cambios = [], []
            edit_map = {i: edit.loc[i] for i in edit.index}
            for i, r in enumerate(regs):
                r2 = {**r, "notas": list(r.get("notas", []))}
                if i in edit_map:
                    for campo in EDITABLES:
                        col = ETIQUETAS[campo] if campo != "padecimiento" else "Padecimiento"
                        antes, ahora_v = vista(r, campo), texto(edit_map[i][col])
                        if antes != ahora_v:
                            aplicar_valor(r2, campo, ahora_v)
                            cambios.append((r2["folio"] or r["folio"], campo, antes or None, ahora_v or None, "corrección en revisión"))
                nuevos.append(r2)
            editados[lote["id"]] = (nuevos, cambios)
            if cambios:
                st.info(f"{len(cambios)} corrección(es) pendiente(s) de confirmar en el paso 3.")
        else:
            doc = lote["doc"]
            r = regs[0]
            izq, der = st.columns([1, 1])
            if doc.get("imagen") is not None:
                izq.image(doc["imagen"], caption="Documento original", width="stretch")
            else:
                izq.info("No hay imagen disponible del documento.")
            if doc["sin_datos"]:
                der.warning(f"{SIN_DATOS}. Captura al menos folio y nombre para poder guardar.")
            if doc.get("error"):
                der.error(doc["error"])
            r2 = {**r, "notas": list(r.get("notas", [])), "extraccion": {}}
            cambios = []
            for campo in EDITABLES:
                prop = vista(r, campo)
                if campo == "tipo_evento":
                    val = der.selectbox(ETIQUETAS[campo], TIPOS_EVENTO, index=TIPOS_EVENTO.index(r["tipo_evento"]), key=f"doc_{lote['id']}_{campo}")
                else:
                    val = der.text_input(ETIQUETAS[campo], value=prop, key=f"doc_{lote['id']}_{campo}",
                                         placeholder=NO_REGISTRADO if campo == "padecimiento" else "")
                val = texto(val)
                if prop and val == prop:
                    estado = "Extraído automáticamente"
                elif prop and val != prop:
                    estado = "Corregido en revisión"
                elif val:
                    estado = "Captura manual"
                else:
                    estado = "Sin dato"
                r2["extraccion"][campo] = estado
                if val != prop:
                    aplicar_valor(r2, campo, val)
                    cambios.append((r2["folio"] or "(sin folio)", campo, prop or None, val or None,
                                    "captura manual" if not prop else "corrección en revisión"))
                der.caption(f"↳ {estado}")
            if not (r2.get("folio") and r2.get("nombre")):
                r2["folio"] = r2.get("folio") or ""
                der.error("Faltan folio o nombre: este documento no se guardará.")
            alertas = banderas(r2) + r2.get("notas", [])
            m = mejor_coincidencia(r2.get("nombre"), candidatos_nombre(lote["id"]), excluir=r2.get("folio"))
            if m:
                alertas.append(f"Posible coincidencia con {m[0]} ({m[1]:.0f} %)")
            if r2.get("folio"):
                alertas.append("Estado al guardar: " + db.clasificar(conn, [r2])[0])
            der.markdown("**Alertas:** " + (", ".join(alertas) or "ninguna"))
            if not (r2.get("folio") and r2.get("nombre")):
                r2["folio"] = ""
            editados[lote["id"]] = ([r2], [c for c in cambios if r2["folio"]])
        st.divider()

    # Conflictos de folio
    conf = db.conflictos_df(conn)
    st.markdown("### Folios existentes que llegaron con datos diferentes")
    if not len(conf):
        st.success("No hay conflictos de folio pendientes.")
    for _, c in conf.iterrows():
        act, ent = db.extra(c["datos_actuales_json"]), db.extra(c["datos_entrantes_json"])
        dif = [{"Campo": ETIQUETAS.get(k, k), "Valor guardado": act.get(k), "Valor que llegó": ent.get(k)}
               for k in act if act.get(k) != ent.get(k)]
        with st.expander(f"{c['folio']} · llegó desde {c['archivo']}, {c['ubicacion']}"):
            st.dataframe(pd.DataFrame(dif).astype(str), hide_index=True, width="stretch")
            k = st.columns(2)
            if k[0].button("Mantener lo guardado", key=f"mant_{c['id']}"):
                db.resolver_conflicto(conn, int(c["id"]), aplicar=False)
                st.rerun()
            if k[1].button("Aplicar lo que llegó", key=f"apl_{c['id']}"):
                db.resolver_conflicto(conn, int(c["id"]), aplicar=True)
                st.rerun()

    # Coincidencias de identidad
    st.markdown("### Posibles coincidencias entre personas")
    st.caption("EIRA no tiene un identificador común de paciente. Estas sugerencias se basan en la similitud de escritura "
               "del nombre; solo tu confirmación vincula registros. El folio identifica una actividad, no a una persona.")
    sug = db.sugerencias_df(conn)
    if not len(sug):
        st.info("No hay sugerencias. Aparecen después de confirmar registros en el paso 3.")
    else:
        f1, f2 = st.columns(2)
        prios = f1.multiselect("Prioridad", sorted(sug["prioridad"].unique()), key="f_prio")
        ests = f2.multiselect("Estado", db.DECISIONES, default=[db.PENDIENTE], key="f_est")
        vis = sug[(sug["prioridad"].isin(prios) if prios else True) & (sug["estado"].isin(ests) if ests else True)]
        tabla_s = pd.DataFrame({
            "Decisión": vis["estado"], "Prioridad": vis["prioridad"],
            "Folio A": vis["folio_a"], "Nombre original A": vis["original_a"].fillna(vis["nombre_a"]), "Edad A": vis["edad_a"],
            "Municipio A": vis["municipio_a"].fillna(SIN_MUNICIPIO), "Fuente A": vis["fuente_a"],
            "Folio B": vis["folio_b"], "Nombre original B": vis["original_b"].fillna(vis["nombre_b"]), "Edad B": vis["edad_b"],
            "Municipio B": vis["municipio_b"].fillna(SIN_MUNICIPIO), "Fuente B": vis["fuente_b"],
            "Similitud %": vis["puntaje"], "Motivo de la sugerencia": vis["motivo"]})
        st.caption(f"{len(vis)} de {len(sug)} sugerencias · {db.identidades_pendientes(conn)} pendientes")
        ed_s = st.data_editor(tabla_s, key=f"sug_{'_'.join(prios)}_{'_'.join(ests)}_{len(sug)}", hide_index=True,
                              width="stretch", num_rows="fixed",
                              disabled=[c for c in tabla_s.columns if c != "Decisión"],
                              column_config={"Decisión": st.column_config.SelectboxColumn(options=db.DECISIONES, required=True)})
        k = st.columns([1, 1, 2])
        if k[0].button("Guardar decisiones", type="primary"):
            n = db.guardar_decisiones(conn, list(zip(ed_s["Folio A"], ed_s["Folio B"], ed_s["Decisión"])))
            ss.flash.append(("success", f"{n} decisión(es) guardada(s) en la bitácora."))
            st.rerun()
        masiva = k[1].selectbox("Aplicar a todas las filas mostradas", db.DECISIONES, key="masiva", label_visibility="collapsed")
        if k[2].button(f"Aplicar «{masiva}» a las {len(vis)} filas mostradas"):
            n = db.guardar_decisiones(conn, [(a, b, masiva) for a, b in zip(vis["folio_a"], vis["folio_b"])])
            ss.flash.append(("success", f"{n} decisión(es) guardada(s) en la bitácora."))
            st.rerun()

# ---------------------------------------------------------------- 3. Confirmar
with paso3:
    st.subheader("Paso 3 · Confirmar")
    if not editados:
        st.info("No hay registros en revisión.")
    else:
        total = {"Nuevos": 0, "Sin cambios": 0, "Conflictos": 0, "No se guardarán": 0, "Correcciones": 0}
        for lid, (regs, cambios) in editados.items():
            est = db.clasificar(conn, regs)
            total["Nuevos"] += sum(e == "Nuevo" for e in est)
            total["Sin cambios"] += sum(e.startswith(("Sin cambios", "Repetido", "Conflicto ya")) for e in est)
            total["Conflictos"] += sum(e.startswith("Folio existente") for e in est)
            total["No se guardarán"] += sum(e.startswith("Sin folio") for e in est)
            total["Correcciones"] += len(cambios)
        c = st.columns(len(total))
        for col, (k, v) in zip(c, total.items()):
            col.metric(k, v)
        todos_cambios = [c for _, cs in editados.values() for c in cs]
        if todos_cambios:
            st.markdown("**Correcciones que se registrarán en la bitácora**")
            st.dataframe(pd.DataFrame(todos_cambios, columns=["Folio", "Campo", "Valor anterior", "Valor nuevo", "Origen"]),
                         hide_index=True, width="stretch")
        st.caption("Al confirmar se guarda la fecha y hora. Los folios existentes con datos diferentes no se sobrescriben: "
                   "quedan en «Revisar datos» para que decidas.")
        if st.button("Confirmar y guardar", type="primary"):
            for lid, (regs, cambios) in editados.items():
                lote = ss.lotes[lid]
                res = db.confirmar(conn, regs, cambios, lote["archivo"], lote["sha"], lote["tipo"])
                ss.flash.append(("success", f"{lote['archivo']}: {res['nuevos']} nuevos, {res['sin_cambios']} sin cambios, "
                                            f"{res['conflictos']} con datos diferentes enviados a revisión"
                                            + (f", {res['omitidos']} sin folio omitidos" if res["omitidos"] else "") + "."))
                del ss.lotes[lid]
            st.rerun()

# ---------------------------------------------------------------- 4. Tablero
with paso4:
    st.subheader("Paso 4 · Ver tablero")
    todo = db.actividades_df(conn)
    if not len(todo):
        st.info("Aún no hay actividades confirmadas. Usa «Cargar datos de ejemplo» en el paso 1.")
    else:
        base = report.preparar(todo)
        f = st.columns([2, 2, 1, 2])
        municipios = f[0].multiselect("Municipio", sorted(base["municipio_vista"].unique()))
        programas = f[1].multiselect("Programa", sorted(base["programa_vista"].unique()))
        modo = f[2].radio("Periodo", ["Todo el periodo", "Rango de fechas"])
        rango = None
        if modo == "Rango de fechas":
            fechas = pd.to_datetime(base.loc[base["fecha_valida"] == 1, "fecha"])
            ini, fin = (fechas.min().date(), fechas.max().date()) if len(fechas) else (date.today(), date.today())
            sel = f[3].date_input("Desde / hasta", (ini, fin), format="DD/MM/YYYY")
            rango = tuple(sel) if isinstance(sel, (tuple, list)) and len(sel) == 2 else None
        filtros = {"municipios": municipios, "programas": programas, "rango": rango}
        df_f, excluidas = report.filtrar(todo, **filtros)
        pend = db.identidades_pendientes(conn)
        res = report.resumen(df_f, db.mapa_personas(conn), pend)

        m = st.columns(4)
        m[0].metric("Atenciones", res["atenciones"])
        m[1].metric("Participaciones", res["participaciones"])
        if res["citas"]:
            m[2].metric("Citas agendadas", res["citas"], help="Solo registros que la fuente identifica como cita; no suman a atenciones")
        if res["unicas"] is None:
            m[3].metric("Beneficiarias únicas", "Pendiente")
            st.warning(f"Total de beneficiarias únicas pendiente de validación ({pend} posibles coincidencias por revisar en el paso 2).")
        else:
            m[3].metric("Beneficiarias únicas", res["unicas"])
        if excluidas:
            st.caption(f"{excluidas} actividad(es) con fecha inválida excluidas del filtro por fecha (siguen en el total general).")

        t_res, t_ind, t_bit, t_exp = st.tabs(["Resumen", "Consulta individual", "Bitácora y fuentes", "Exportar informe"])
        with t_res:
            pm = res["por_municipio"]
            if len(pm):
                largo = pm.melt(id_vars="Municipio", var_name="Tipo", value_name="Actividades")
                largo = largo[largo["Actividades"] > 0] if res["citas"] == 0 else largo
                graf = (alt.Chart(largo).mark_bar().encode(
                    x=alt.X("Municipio:N", sort="-y", title=None), y=alt.Y("Actividades:Q"),
                    color=alt.Color("Tipo:N", scale=alt.Scale(range=["#d6336c", "#7048e8", "#20c997"])),
                    xOffset="Tipo:N", tooltip=["Municipio", "Tipo", "Actividades"]).properties(height=320))
                st.altair_chart(graf, width="stretch")
                st.dataframe(pm, hide_index=True, width="stretch")
            st.markdown("**Alertas de calidad**")
            adv = report.advertencias(conn, todo)
            if adv:
                for a in adv:
                    st.warning(a)
            else:
                st.success("Sin alertas de calidad.")

        with t_ind:
            st.caption("Vista reservada: contiene nombres y datos de salud. No se incluye en el informe exportado.")
            busc = st.text_input("Buscar por nombre o folio")
            cand = base[base["nombre"].fillna("").str.contains(busc, case=False, regex=False) |
                        base["folio"].str.contains(busc, case=False, regex=False)] if busc else base
            if not len(cand):
                st.info("Sin resultados.")
            else:
                opciones = [f"{r.folio} · {r.nombre or '(sin nombre)'}" for r in cand.sort_values(["nombre", "folio"]).itertuples()]
                elegido = st.selectbox(f"{len(cand)} resultado(s)", opciones).split(" · ")[0]
                personas = db.mapa_personas(conn)
                grupo = [f for f, rep in personas.items() if rep == personas[elegido]]
                acts = base[base["folio"].isin(grupo)].sort_values("fecha", na_position="last")
                st.markdown(f"#### {acts.iloc[0]['nombre'] or '(sin nombre)'}")
                st.write(f"Actividades vinculadas por revisión humana: **{len(grupo)}**"
                         + ("" if len(grupo) > 1 else " (solo esta actividad; no hay vínculos confirmados)"))
                st.dataframe(pd.DataFrame({
                    "Folio": acts["folio"], "Tipo": acts["tipo_evento"],
                    "Fecha": [fecha_vista(dict(r)) + ("" if r["fecha_valida"] else " (fecha inválida)") for _, r in acts.iterrows()],
                    "Servicio o actividad": acts["servicio"], "Programa": acts["programa"],
                    "Edad": acts["edad"], "Municipio": acts["municipio_vista"],
                    "Padecimiento": acts["padecimiento"].fillna(NO_REGISTRADO),
                    "Fuente (edad y municipio)": acts["archivo_origen"] + ", " + acts["ubicacion_origen"],
                    "Método": acts["metodo"]}).astype(str), hide_index=True, width="stretch")
                citas = acts[acts["tipo_evento"] == CITA]
                if len(citas):
                    st.markdown("**Citas agendadas (según la fuente)**")
                    st.dataframe(citas[["folio", "fecha", "servicio", "archivo_origen"]], hide_index=True)
                else:
                    st.caption("La fuente no identifica citas agendadas para esta persona.")
                s = db.sugerencias_df(conn)
                rel = s[(s["folio_a"].isin(grupo) | s["folio_b"].isin(grupo)) & (s["estado"] == db.PENDIENTE)]
                if len(rel):
                    st.info("Coincidencias pendientes (no vinculadas): " +
                            "; ".join(f"{r.folio_a} ↔ {r.folio_b} ({r.motivo})" for r in rel.itertuples()))

        with t_bit:
            st.markdown("**Fuentes cargadas**")
            st.dataframe(report.fuentes(conn), hide_index=True, width="stretch")
            st.markdown("**Bitácora de cambios y decisiones**")
            bit = db.cambios_df(conn)
            if len(bit):
                st.dataframe(bit, hide_index=True, width="stretch")
            else:
                st.caption("Sin cambios registrados.")
            hist = db.conflictos_df(conn, pendientes=False)
            if len(hist):
                st.markdown("**Conflictos de folio (historial)**")
                st.dataframe(hist[["folio", "archivo", "ubicacion", "estado", "creado_en", "decidido_en"]], hide_index=True, width="stretch")

        with t_exp:
            st.write("El informe agregado incluye filtros aplicados, fecha de corte, fuentes, conteos, advertencias y "
                     "ajustes manuales. No incluye nombres ni datos de salud.")
            ctx = report.contexto(conn, filtros, res, excluidas)
            sufijo = date.today().strftime("%Y%m%d")
            e = st.columns(2)
            e[0].download_button("Descargar Excel", report.excel_bytes(ctx), f"informe_eira_{sufijo}.xlsx",
                                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
            e[1].download_button("Descargar PDF", report.pdf_bytes(ctx), f"informe_eira_{sufijo}.pdf", "application/pdf")
