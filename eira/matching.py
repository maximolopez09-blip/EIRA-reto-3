import re

from rapidfuzz import fuzz, process

from .config import SIN_MUNICIPIO, UMBRAL_SIMILITUD
from .quality import norm, texto

PRIORIDAD_ALTA = "Alta: mismo nombre, edad y municipio"
PRIORIDAD_REVISAR = "Revisar: escritura similar"
PRIORIDAD_HOMONIMAS = "Baja: posibles homónimas"


def clave_nombre(s) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", norm(s)).split())


def similitud(a, b) -> float:
    return fuzz.token_sort_ratio(clave_nombre(a), clave_nombre(b))


def describir(a: dict, b: dict, puntaje: float):
    """Motivo legible y prioridad de una sugerencia (a y b tienen nombre, edad, municipio)."""
    na, nb = texto(a["nombre"]), texto(b["nombre"])
    if na == nb:
        partes = ["Nombre escrito exactamente igual"]
    elif clave_nombre(na) == clave_nombre(nb):
        partes = ["Mismo nombre al ignorar mayúsculas, acentos y espacios"]
    else:
        partes = [f"Escritura similar ({puntaje:.0f} %)"]
    ea, eb = a.get("edad"), b.get("edad")
    misma_edad = ea is not None and eb is not None and abs(int(ea) - int(eb)) <= 1
    if ea is None or eb is None:
        partes.append("edad no disponible en ambos")
    else:
        partes.append(f"misma edad ({ea})" if ea == eb else f"edad {'similar' if misma_edad else 'distinta'} ({ea} vs {eb})")
    ma, mb = a.get("municipio") or SIN_MUNICIPIO, b.get("municipio") or SIN_MUNICIPIO
    mismo_mun = ma == mb and ma != SIN_MUNICIPIO
    partes.append(f"mismo municipio ({ma})" if mismo_mun else f"municipio distinto ({ma} vs {mb})")
    if misma_edad and mismo_mun:
        prioridad = PRIORIDAD_ALTA if clave_nombre(na) == clave_nombre(nb) else PRIORIDAD_REVISAR
    elif clave_nombre(na) == clave_nombre(nb):
        prioridad = PRIORIDAD_HOMONIMAS
    else:
        prioridad = PRIORIDAD_REVISAR
    return "; ".join(partes), prioridad


def sugerir(registros: list[dict], umbral: float = UMBRAL_SIMILITUD) -> list[dict]:
    """Pares (folio_a < folio_b) con nombres parecidos. Solo sugiere: nunca vincula."""
    regs = [r for r in registros if texto(r.get("nombre"))]
    claves = [clave_nombre(r["nombre"]) for r in regs]
    if len(regs) < 2:
        return []
    matriz = process.cdist(claves, claves, scorer=fuzz.token_sort_ratio, score_cutoff=umbral, workers=1)
    out = []
    for i in range(len(regs)):
        for j in range(i + 1, len(regs)):
            p = float(matriz[i][j])
            if p < umbral or regs[i]["folio"] == regs[j]["folio"]:
                continue
            a, b = sorted([regs[i], regs[j]], key=lambda r: r["folio"])
            motivo, prioridad = describir(a, b, p)
            out.append({"folio_a": a["folio"], "folio_b": b["folio"], "puntaje": round(p, 1), "motivo": motivo, "prioridad": prioridad})
    return out


def mejor_coincidencia(nombre, candidatos: list[tuple[str, str]], excluir: str | None = None, umbral: float = UMBRAL_SIMILITUD):
    """candidatos: [(folio, nombre)]. Devuelve (folio, puntaje) o None."""
    pool = [(f, clave_nombre(n)) for f, n in candidatos if f != excluir and texto(n)]
    if not texto(nombre) or not pool:
        return None
    res = process.extractOne(clave_nombre(nombre), [p[1] for p in pool], scorer=fuzz.token_sort_ratio, score_cutoff=umbral)
    return (pool[res[2]][0], res[1]) if res else None


def componentes(folios: list[str], vinculos: list[tuple[str, str]]) -> dict[str, str]:
    """Union-find: folio -> folio representante, solo con vínculos confirmados por una persona."""
    padre = {f: f for f in folios}

    def raiz(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for a, b in vinculos:
        if a in padre and b in padre:
            ra, rb = raiz(a), raiz(b)
            if ra != rb:
                padre[max(ra, rb)] = min(ra, rb)
    return {f: raiz(f) for f in folios}
