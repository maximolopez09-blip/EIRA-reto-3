"""Palabras con su posición (en puntos, origen arriba a la izquierda) de una página PDF con texto."""
import re


def palabras_pdf(pagina) -> list[dict]:
    """Devuelve [{'t': texto, 'caja': [x0, y0, x1, y1]}]. Las rayas de subrayado («____») salen como palabras aparte."""
    alto = pagina.get_height()
    tp = pagina.get_textpage()
    res, act = [], None

    def cerrar():
        nonlocal act
        if act:
            res.append({"t": act["t"], "caja": [round(v, 1) for v in act["caja"]]})
        act = None

    for i in range(tp.count_chars()):
        c = tp.get_text_range(i, 1)
        if not c or c.isspace() or c in "\ufffe\x00":
            cerrar()
            continue
        x0, y0, x1, y1 = tp.get_charbox(i, loose=True)
        caja = [x0, alto - y1, x1, alto - y0]
        raya = c == "_"
        if act and (act["raya"] != raya or caja[0] - act["caja"][2] > 3 or abs(caja[1] - act["caja"][1]) > 4):
            cerrar()
        if act:
            act["t"] += c
            act["caja"] = [min(act["caja"][0], caja[0]), min(act["caja"][1], caja[1]), max(act["caja"][2], caja[2]), max(act["caja"][3], caja[3])]
        else:
            act = {"t": c, "caja": caja, "raya": raya}
    cerrar()
    return res


def es_raya(t: str) -> bool:
    return bool(re.fullmatch(r"_+", t))
