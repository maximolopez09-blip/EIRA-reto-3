"""Mide la lectura automática contra lo que se escribió en cada ejemplo (`valores_esperados.json`).

    python scripts/medir_lectura.py                  # Datos/ejemplos
    python scripts/medir_lectura.py carpeta_lote -v  # un lote de `generar_ejemplos.py --lote N --salida carpeta_lote`
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eira import documents
from eira.config import EJEMPLOS
from eira.formularios import PLANTILLAS
from eira.quality import norm, normalizar_municipio
from rapidfuzz import fuzz

ap = argparse.ArgumentParser()
ap.add_argument("carpeta", nargs="?", default=str(EJEMPLOS))
ap.add_argument("-v", action="store_true", help="lista cada campo mal leído")
a = ap.parse_args()
carpeta = Path(a.carpeta)
esperados = json.loads((carpeta / "valores_esperados.json").read_text(encoding="utf-8"))
clave = lambda s: norm(s).replace(" ", "")
ok, dudas, registro, parecido = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
for nombre, e in esperados.items():
    archivos = [(nombre, (carpeta / nombre).read_bytes())] + [(p.name, p.read_bytes()) for p in sorted(carpeta.glob(Path(nombre).stem + "_pagina*"))]
    doc = documents.procesar_varios(archivos)
    f = doc.get("formulario")
    if not f or f["formato"] != e["formato"]:
        print(f"{nombre}: formato no reconocido ({doc['error'] or doc['metodo']})")
        continue
    tipos = {c["nombre"]: c["tipo"] for p in PLANTILLAS[f["formato"]]["paginas"] for c in p["campos"]}
    grupo = "foto" if "foto" in nombre else "escaneo"
    for n, tipo in tipos.items():
        esp, leido = e["valores"].get(n, ""), f["valores"].get(n, "")
        if not esp and not leido:
            continue
        bien = clave(esp) == clave(leido)
        ok[(tipo, grupo)].append(bien)
        parecido[(tipo, grupo)].append(fuzz.ratio(clave(esp), clave(leido)))
        dudosa = f["confianza"].get(n, 0) < 0.6
        dudas[(tipo, grupo)].append((not bien) and not dudosa)  # error que pasaría sin aviso
        if a.v and not bien:
            print(f"  {nombre:32} {n:28} {esp!r:38} -> {leido!r} ({f['confianza'].get(n, 0):.2f})")
    v = e["valores"]
    pre = "atencion" if f["formato"] == "mamaria" else "toma"
    esperado = {"folio": v["folio"], "nombre": v["nombre"], "edad": v["edad"], "fecha": f"{v[pre + '_dia']}/{v[pre + '_mes']}/{v[pre + '_anio']}",
                "municipio": normalizar_municipio(v["residencia#2"].split(",")[0])[0]}
    for k, esp in esperado.items():
        registro[(k, grupo)].append(clave(esp) == clave(str(doc["campos"].get(k) or "")))
        if a.v and not registro[(k, grupo)][-1]:
            print(f"  {nombre:32} REGISTRO {k:19} {esp!r:38} -> {doc['campos'].get(k)!r}")
print(f"{'tipo de campo':22} {'n':>5} {'exactos':>8} {'parecido':>9} {'errores sin aviso':>18}")
for k in sorted(ok):
    n = len(ok[k])
    print(f"{k[0] + ' / ' + k[1]:22} {n:5d} {sum(ok[k]) / n:8.0%} {sum(parecido[k]) / n:8.0f}% {sum(dudas[k]) / n:18.0%}")
print("\nCampos del registro EIRA (exactos):")
for k in sorted(registro):
    print(f"  {k[0] + ' / ' + k[1]:22} {sum(registro[k])}/{len(registro[k])}")
