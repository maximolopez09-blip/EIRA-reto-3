"""Lectura de formularios: PDF con texto, o foto / PDF escaneado de un formato llenado a mano (todo local)."""
import io
import os
import re
import shutil
from pathlib import Path

from PIL import Image, ImageOps

from .config import ATENCION, TESSDATA
from .quality import norm, normalizar_municipio, normalizar_nombre, parse_edad, parse_fecha, texto

RUTAS_TESSERACT = [r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]
MIN_TEXTO = 30
MAX_PAGINAS = 4


def tesseract_cmd() -> str | None:
    env = os.environ.get("TESSERACT_CMD")
    if env:
        return env if Path(env).exists() else None
    return shutil.which("tesseract") or next((p for p in RUTAS_TESSERACT if Path(p).exists()), None)


def ocr(img: Image.Image) -> str:
    """OCR en español. Lanza RuntimeError con una explicación legible si no es posible."""
    import pytesseract

    cmd = tesseract_cmd()
    if not cmd:
        raise RuntimeError("No se encontró Tesseract OCR en este equipo (instálalo o define TESSERACT_CMD).")
    pytesseract.pytesseract.tesseract_cmd = cmd
    config = "--psm 6"
    if (TESSDATA / "spa.traineddata").exists():
        os.environ["TESSDATA_PREFIX"] = str(TESSDATA)
    g = ImageOps.grayscale(img)
    if max(g.size) < 1500:
        f = 1500 / max(g.size)
        g = g.resize((int(g.width * f), int(g.height * f)), Image.LANCZOS)
    try:
        return pytesseract.image_to_string(g, lang="spa", config=config)
    except pytesseract.TesseractError as e:
        if "spa" in str(e) or "traineddata" in str(e):
            raise RuntimeError("Tesseract no tiene instalado el idioma español (spa.traineddata).") from e
        raise RuntimeError(f"Tesseract no pudo leer el documento: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Falló el OCR: {e}") from e


def _valor(linea: str) -> str:
    return texto(re.sub(r"_{2,}|\s[_.]+\s|^[\s:._-]+|[\s:._-]+$", " ", linea))


def _despues(t: str, patron: str, hasta: str | None = None) -> str:
    """Texto que sigue a una etiqueta en la misma línea, hasta la siguiente etiqueta opcional."""
    m = re.search(patron + r"[ \t]*[:.]?[ \t]*(.*)", t, re.I)
    if not m:
        return ""
    v = m.group(1)
    if hasta:
        v = re.split(hasta, v, maxsplit=1, flags=re.I)[0]
    return _valor(v)


def extraer_campos(t: str) -> dict:
    campos = dict.fromkeys(["folio", "fecha", "tipo_evento", "programa", "municipio", "nombre", "edad", "servicio", "padecimiento"])
    if not texto(t):
        return campos
    m = re.search(r"folio\s*(?:eira)?\s*[:.]?\s*([A-Z]{2}\s?-\s?\d{3,})", t, re.I)
    if m:
        campos["folio"] = re.sub(r"\s", "", m.group(1)).upper()
    m = re.search(r"fecha\s+de\s+atenci\S{1,2}n\s*[:.]?\s*(?:d\S{1,2}a)?\s*(\d{1,2})\s*(?:[/\-.]|\s+mes)\s*(\d{1,2})\s*(?:[/\-.]|\s+a\S{1,2}o)\s*(\d{4})", t, re.I)
    if m:
        campos["fecha"] = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    nombre = _despues(t, r"(?:^|\n)\s*(?:2\s*[.,]\s*)?nombre(?!\s*,?\s*firma)", r"\d+\s*\.\s|entidad|edad")
    if nombre and re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{2}", nombre):
        campos["nombre"] = normalizar_nombre(nombre)
    edad = _despues(t, r"edad\s+en\s+a\S{1,3}s")
    campos["edad"] = parse_edad(edad) if edad else None
    mun = _despues(t, r"residencia\s+habitual", r"\d+\s*\.\s|tel\S{1,2}fono")
    if mun and re.search(r"[A-Za-z]{3}", mun):
        campos["municipio"] = mun
    # Solo se transcribe un padecimiento escrito explícitamente tras la etiqueta (con «:»),
    # nunca a partir del nombre del estudio ni de las opciones impresas del formato.
    m = re.search(r"diagn\S{1,2}stico(?:[ \t]+registrado)?[ \t]*:[ \t]*([^\n]*)", t, re.I)
    diag = _valor(m.group(1)) if m else ""
    birads = re.search(r"birads[ \t]*:[ \t]*([0-6])\b", t, re.I)
    if diag and re.search(r"[A-Za-z0-9]{2}", diag):
        campos["padecimiento"] = diag
    elif birads:
        campos["padecimiento"] = f"BIRADS {birads.group(1)}"
    n = norm(t)
    if "deteccion oportuna" in n:
        campos["programa"] = "Detección oportuna"
    if "revision mamaria" in n:
        campos["servicio"] = "Revisión mamaria"
    elif "citologia" in n:
        campos["servicio"] = "Toma de citología"
    campos["tipo_evento"] = ATENCION
    return campos


def _paginas(nombre: str, contenido: bytes) -> tuple[list[Image.Image], str, int]:
    """Imágenes de las páginas (hasta MAX_PAGINAS), texto incrustado de la primera y número total de páginas."""
    if nombre.lower().endswith(".pdf"):
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(contenido)
        txt = pdf[0].get_textpage().get_text_range()
        return [pdf[i].render(scale=3).to_pil() for i in range(min(len(pdf), MAX_PAGINAS))], txt, len(pdf)
    img = Image.open(io.BytesIO(contenido))
    img = ImageOps.exif_transpose(img)  # las fotos de celular guardan el giro aparte
    return [img.convert("RGB")], "", 1


def _formulario(imagenes: list[Image.Image]) -> dict | None:
    """Lee las páginas como un formato de EIRA llenado a mano. None si ninguna página es un formato conocido."""
    try:
        from . import lectura, manuscrito
    except ImportError:  # sin OpenCV: solo queda el OCR de página completa
        return None
    paginas = {}
    for img in imagenes:
        pag = lectura.leer_pagina(img, tesseract_cmd())
        if pag and (not paginas or pag.formato == next(iter(paginas.values())).formato):
            paginas.setdefault(pag.indice, pag)
    if not paginas:
        return None
    f = manuscrito.leer_formato([paginas[i] for i in sorted(paginas)], tesseract_cmd())
    f["paginas"] = sorted(paginas)
    return f


def _resumen(f: dict) -> str:
    lineas = [f["titulo"]]
    for k, v in f["valores"].items():
        if "#" in k:
            continue
        op = f["opciones"].get(k, {}).get(v)
        duda = "" if f["confianza"].get(k, 0) >= 0.6 else "  (?)"
        lineas.append(f"{k}: {v}" + (f" = {op}" if op else "") + duda)
    return "\n".join(lineas)


def procesar_varios(archivos: list[tuple[str, bytes]]) -> dict:
    """Procesa uno o varios archivos que forman un solo documento (p. ej. las fotos de las dos páginas de un formato)."""
    res = {"imagen": None, "imagenes": [], "texto": "", "metodo": "captura manual", "error": None, "paginas": 1, "formulario": None}
    try:
        imagenes, txt, total = [], "", 0
        for nombre, contenido in archivos:
            ims, t, n = _paginas(nombre, contenido)
            imagenes, txt, total = imagenes + ims, txt or t, total + n
        res.update(imagen=imagenes[0], imagenes=imagenes, paginas=total)
        escaneo = archivos[0][0].lower().endswith(".pdf")
        if len(re.sub(r"[\s_.]", "", txt)) >= MIN_TEXTO:
            res["texto"], res["metodo"] = txt, "texto PDF"
        else:
            res["formulario"] = f = _formulario(imagenes)
            if f:
                res["texto"], res["metodo"] = _resumen(f), "Formato llenado a mano (" + ("PDF escaneado" if escaneo else "foto") + ")"
            else:
                res["texto"], res["metodo"] = ocr(imagenes[0]), "OCR (PDF escaneado)" if escaneo else "OCR"
    except RuntimeError as e:
        res["error"], res["metodo"] = str(e), "captura manual"
    except Exception as e:
        res["error"], res["metodo"] = f"No se pudo leer el documento: {e}", "captura manual"
    if res["formulario"] and not res["error"]:
        res["campos"] = res["formulario"]["campos"]
    else:
        res["campos"] = extraer_campos(res["texto"]) if not res["error"] else extraer_campos("")
    if res["error"]:
        res["campos"]["tipo_evento"] = ATENCION
    res["sin_datos"] = not (res["campos"].get("folio") or res["campos"].get("nombre"))
    return res


def procesar(nombre: str, contenido: bytes) -> dict:
    return procesar_varios([(nombre, contenido)])


def a_registro(doc: dict, archivo: str) -> dict:
    c, f = doc["campos"], doc.get("formulario")
    fecha, valida = parse_fecha(c.get("fecha"))
    municipio, nota = normalizar_municipio(c.get("municipio"))
    return {
        "folio": (c.get("folio") or "").upper(),
        "fecha": fecha, "fecha_original": c.get("fecha") or "", "fecha_valida": valida,
        "tipo_evento": c.get("tipo_evento") or ATENCION,
        "programa": c.get("programa"), "municipio": municipio, "nombre": c.get("nombre"),
        "edad": c.get("edad"), "servicio": c.get("servicio"), "padecimiento": c.get("padecimiento"),
        "archivo": archivo, "ubicacion": "página 1", "metodo": doc["metodo"],
        "nombre_original": c.get("nombre"),
        "notas": ([nota] if nota else []) + [f"Lectura dudosa de {k}: revisar contra el documento" for k in (f or {}).get("dudosos", [])],
        "originales": {"texto_extraido": (doc.get("texto") or "")[:4000], **({"formulario": f["valores"]} if f else {})},
    }
