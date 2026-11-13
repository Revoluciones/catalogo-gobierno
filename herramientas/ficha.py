#!/usr/bin/env python3
"""Genera la ficha para compartir de un procedimiento: página, imágenes y texto para WhatsApp.

Uso:
  python3 herramientas/ficha.py <id> [<id> ...] [--salida salida/dentro] [--base https://compartido.org/dentro]
  python3 herramientas/ficha.py --todas        # todas las fichas que tienen pasos

Por cada id escribe en <salida>/<id>/:
  index.html    la ficha (funciona sola, también al imprimirla)
  og.png        1200×630, la vista previa del enlace en WhatsApp, Facebook, X y Telegram
  ruta.png      1080×1350, la ruta completa en una imagen para mandar o subir a estados
  whatsapp.txt  el mensaje listo para pegar en WhatsApp

Las imágenes necesitan Playwright con Chromium (pip install playwright; playwright install chromium).
Sin Playwright se escriben index.html y whatsapp.txt, y se avisa.
"""
import argparse, html, json, os, re, sys, urllib.parse
from pathlib import Path
import yaml

R = Path(__file__).resolve().parent.parent
TPL = (R / "herramientas/ficha.plantilla.html").read_text(encoding="utf-8")
GLOS = yaml.safe_load((R / "glosario.yaml").read_text(encoding="utf-8"))
REPO = "https://github.com/Revoluciones/catalogo-gobierno"

LUGAR = {"MX": "México (regla nacional)", "MX-BCN": "Baja California", "MX-BCN-Tijuana": "Tijuana, Baja California"}
EVIDENCIA = {
    "documento_oficial": "documento oficial", "auditoria_o_sentencia": "auditoría o sentencia",
    "periodismo_o_investigacion": "periodismo o investigación", "varios_reportes": "varios reportes",
    "un_reporte": "1 reporte",
}
TIPO_FUENTE = {
    "constitucion": "Constitución", "ley": "Ley", "reglamento": "Reglamento", "registro_oficial": "Registro oficial",
    "portal_oficial": "Portal oficial", "manual_procedimientos": "Manual", "manual_organizacion": "Manual",
    "periodismo": "Periodismo", "sentencia": "Sentencia", "auditoria": "Auditoría", "reportes_ciudadanos": "Reportes",
    "solicitud_transparencia": "Transparencia", "informe_oficial": "Informe oficial", "investigacion": "Investigación",
    "acuerdo_o_lineamiento": "Acuerdo", "periodico_oficial": "Periódico oficial",
}
MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()

e = lambda s: html.escape(str(s or ""), quote=True)


def fecha(iso):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{int(m[3])} de {MESES[int(m[2]) - 1]} de {m[1]}" if m else str(iso or "")


def pesos(n):
    return f"${n:,.0f}" if n is not None else ""


def corta(texto, n=110):
    """Primera oración, para las imágenes y WhatsApp."""
    t = re.split(r"(?<=[.!?])\s", str(texto).strip())[0]
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


CORTO = {"MX": "mexico", "MX-BCN": "bc", "MX-BCN-Tijuana": "tijuana"}


def ruta_corta(d):
    """compartido.org/dentro/<lugar>/<nombre>: más corto que el id y sin repetir el lugar."""
    j = d["jurisdiction"]
    prefijo = j.lower() + "-"
    nombre = d["id"][len(prefijo):] if d["id"].startswith(prefijo) else d["id"]
    if j == "MX" and nombre.startswith("mx-"):
        nombre = nombre[3:]
    return f"{CORTO.get(j, j.lower())}/{nombre}"


def duracion(texto):
    """'La oficialía tiene 1 día para resolver' -> '1 día'. Si no hay plazo claro, la primera oración."""
    m = re.search(r"\b(\d+|un|una)\s+(minutos?|horas?|d[ií]as(?: h[aá]biles)?|d[ií]a(?: h[aá]bil)?|semanas?|mes(?:es)?|años?)\b", texto, re.I)
    return m.group(0) if m else corta(texto, 40).rstrip(".")


def es_tu(actor):
    return bool(re.match(r"^\s*t[uú]\b", actor or "", re.I))


_TODOS = None


def todos():
    """Todos los procedimientos, una vez: [(datos, archivo)]."""
    global _TODOS
    if _TODOS is None:
        _TODOS = [(yaml.safe_load(f.read_text(encoding="utf-8")), f) for f in sorted((R / "procedimientos").rglob("*.yaml"))]
    return _TODOS


DISPONIBLE = {"siempre": ("Todo el año", "jade"), "con_cita": ("Con cita", "anil"), "solo_en_campana": ("Solo en campaña", "cemp")}


def caminos(meta_id):
    """Los procedimientos que llevan a la misma meta, del más barato al más caro."""
    rs = [(d, f) for d, f in todos() if (d.get("goal") or {}).get("id") == meta_id]
    # Primero los que se pueden hacer en cualquier momento; luego por costo y por número de documentos.
    return sorted(rs, key=lambda df: (df[0]["route"].get("availability") == "solo_en_campana",
                                      (df[0].get("cost") or {}).get("amount_mxn") or 0, len(df[0].get("requirements", []))))


def costo_corto(d):
    c = d.get("cost") or {}
    if c.get("type") == "gratuito":
        return "Gratis"
    return pesos(c.get("amount_mxn")) if c.get("amount_mxn") is not None else "Varía"


def cargar(pid):
    for f in (R / "procedimientos").rglob(f"{pid}.yaml"):
        return yaml.safe_load(f.read_text(encoding="utf-8")), f
    sys.exit(f"No encontré el procedimiento {pid}")


def datos(d, base):
    src = d.get("sources", {})
    orden = []  # fuentes en orden de primera cita

    def num(key):
        if key not in orden:
            orden.append(key)
        return orden.index(key) + 1

    def chips(cites):
        out = []
        for c in cites or []:
            s = src.get(c["source"], {})
            n = num(c["source"])
            tip = " · ".join(x for x in (c.get("pinpoint"), c.get("quote")) if x)
            out.append(f'<a class="cita" href="#f{n}" title="{e(tip)}">{n}</a>')
        return "".join(out)

    cost = d.get("cost") or {}
    dls = {x["what"]: x for x in d.get("deadlines", [])}
    pasos = d.get("steps", [])
    hechos = []
    if cost:
        valor = "Gratis" if cost.get("type") == "gratuito" else (pesos(cost.get("amount_mxn")) or "Varía")
        hechos.append(("Cuesta", valor, corta(cost.get("text", ""), 90)))
    if pasos:
        hechos.append(("Pasos", str(len(pasos)), ""))
    if "respuesta_autoridad" in dls:
        hechos.append(("Respuesta", duracion(dls["respuesta_autoridad"]["text"]), ""))
    if "vigencia" in dls:
        hechos.append(("Vigencia", duracion(dls["vigencia"]["text"]), dls["vigencia"]["text"]))

    url = f"{base.rstrip('/')}/{ruta_corta(d)}"
    base = base.rstrip("/")
    return dict(base=base, src=src, orden=orden, num=num, chips=chips, cost=cost, dls=dls, pasos=pasos, hechos=hechos, url=url)


def grafo(pasos):
    """Aristas, capa (fila) y columnas de cada paso, a partir de `next` (si falta, sigue el paso siguiente)."""
    ns = [p["n"] for p in pasos]
    aristas = []
    for i, p in enumerate(pasos):
        sig = [n["to"] for n in p.get("next", [])] if p.get("next") else ([ns[i + 1]] if i + 1 < len(ns) else [])
        aristas += [(p["n"], t, next((n.get("when", "") for n in p.get("next", []) if n["to"] == t), "")) for t in sig if t in ns]
    previos = {n: [a for a, b, _ in aristas if b == n] for n in ns}
    capa = {}
    for n in ns:  # los pasos vienen en orden; un paso va una fila abajo de su último paso previo
        capa[n] = max((capa.get(a, 0) + 1 for a in previos[n] if a in capa), default=0)
    col, ocupado = {}, set()
    siguiente_col = 0
    for n in ns:
        pc = sorted({c for a in previos[n] if a in col for c in col[a]})
        if not pc:
            cs = (siguiente_col, siguiente_col)
            siguiente_col += 1
        else:
            cs = (pc[0], pc[-1])
        while any((capa[n], c) in ocupado for c in range(cs[0], cs[1] + 1)):
            cs = (cs[0] + 1, cs[1] + 1)
        for c in range(cs[0], cs[1] + 1):
            ocupado.add((capa[n], c))
        col[n] = range(cs[0], cs[1] + 1)
        siguiente_col = max(siguiente_col, cs[1] + 1)
    return aristas, capa, col, max((c[-1] for c in col.values()), default=0) + 1


def mapa(pasos, grande=False):
    """El diagrama de flujo: cajas en una cuadrícula y flechas que dibuja el navegador."""
    if not pasos:
        return ""
    aristas, capa, col, ncols = grafo(pasos)
    cajas = []
    for p in pasos:
        c = col[p["n"]]
        marca = '<span class="difiere" title="En la práctica pasa otra cosa">≠ práctica</span>' if p.get("practice") else ""
        cajas.append(
            f'<div class="nodo{" nodo--tu" if es_tu(p["actor"]) else ""}" data-n="{e(p["n"])}" '
            f'style="grid-row:{capa[p["n"]] + 1};grid-column:{c[0] + 1}/{c[-1] + 2}">'
            f'<span class="n">{e(p["n"])}</span><div><small>{e(p["actor"])}</small>'
            f'<p>{e(corta(p["action"], 90 if grande else 80))}</p>{marca}</div></div>')
    fin = max(capa.values()) + 1
    flechas = json.dumps([[a, b, w] for a, b, w in aristas], ensure_ascii=False)
    return (f'<div class="mapa" style="--cols:{ncols}" data-aristas="{e(flechas)}">'
            f'<svg class="flechas" aria-hidden="true"></svg>{"".join(cajas)}'
            f'<div class="nodo-fin" style="grid-row:{fin + 1};grid-column:1/-1">Listo</div></div>')


def pagina(d, x):
    chips, num = x["chips"], x["num"]
    lugar = LUGAR.get(d["jurisdiction"], d["jurisdiction"])

    hechos = "".join(
        f'<div class="hecho"><dt>{e(k)}</dt><dd><b>{e(v)}</b>{f"<span>{e(n)}</span>" if n and n != v else ""}</dd></div>'
        for k, v, n in x["hechos"]
    )

    pasos = []
    for p in x["pasos"]:
        tu = es_tu(p["actor"])
        prac = "".join(
            f'<aside class="practica"><p class="etq">En la práctica · {e(EVIDENCIA.get(q["evidence_level"], ""))}'
            f'{" · " + e(q["observed"]) if q.get("observed") else ""}</p><p>{e(q["text"])} {chips(q["cites"])}</p></aside>'
            for q in p.get("practice", [])
        )
        plazo = f'<span class="plazo">{e(p["deadline"])}</span>' if p.get("deadline") else ""
        pasos.append(
            f'<li class="paso{" paso--tu" if tu else ""}"><span class="n" aria-hidden="true">{e(p["n"])}</span>'
            f'<div class="cuerpo"><p class="actor">{e(p["actor"])}</p>'
            f'<p class="accion">{e(p["action"])} {chips(p["cites"])}</p>{plazo}{prac}</div></li>'
        )

    reqs = []
    for i, r in enumerate(d.get("requirements", [])):
        oc = r.get("original_or_copy", "")
        reqs.append(
            f'<li><label><input type="checkbox" data-k="{i}"><span class="caja" aria-hidden="true"></span>'
            f'<span class="txt">{e(r["text"])} {chips(r.get("cites"))}</span>'
            f'{f"<span class=oc>{e(oc)}</span>" if oc else ""}</label></li>'
        )

    ofis = []
    for o in d.get("offices", []):
        partes = [f"<b>{e(o.get('name'))}</b>"]
        dire = ", ".join(v for v in (o.get("address"), o.get("municipality")) if v)
        for v in (dire, o.get("hours"), o.get("phones") and "Tel. " + o["phones"]):
            if v:
                partes.append(f"<span>{e(v)}</span>")
        ofis.append("<li>" + "".join(partes) + "</li>")
    ofis = "".join(ofis)

    glos = "".join(f"<div><dt>{e(k.replace('-', ' '))}</dt><dd>{e(GLOS[k])}</dd></div>" for k in d.get("glossary", []) if k in GLOS)

    base_legal = " ".join(chips([c]) for c in d.get("legal_basis", []))

    fuentes = []
    for k in x["orden"]:
        s = x["src"].get(k, {})
        tipo = TIPO_FUENTE.get(s.get("type"), s.get("type", ""))
        of = "oficial" if s.get("official", True) else "no oficial"
        titulo = f'<a href="{e(s["url"])}" rel="noopener">{e(s.get("title", k))}</a>' if s.get("url") else e(s.get("title", k))
        extra = " · ".join(v for v in (s.get("publisher"), s.get("version_date") and f"versión {s['version_date']}") if v)
        fuentes.append(f'<li id="f{x["orden"].index(k) + 1}"><span class="tipo tipo--{"of" if s.get("official", True) else "no"}">{e(tipo)} · {of}</span>{titulo}{f"<small>{e(extra)}</small>" if extra else ""}</li>')

    estado = {
        "borrador": "Borrador: escrito a partir de las fuentes citadas. Falta que otra persona coteje cada paso.",
        "revisado": "Revisado: otra persona cotejó cada paso con su fuente.",
        "importado": "Copiado tal cual del registro oficial.",
        "desactualizado": "Desactualizado: la fuente cambió y esta ficha todavía no.",
    }[d["status"]]
    archivo = f'{REPO}/blob/main/{x["ruta_archivo"]}'

    otros = ""
    meta = d.get("goal")
    if meta:
        hermanos = [h for h, _ in caminos(meta["id"]) if h["id"] != d["id"]]
        if hermanos:
            chips = "".join(
                f'<a class="camino" href="{e(x["base"])}/{e(ruta_corta(h))}"><b>{e(h["route"]["name"])}</b>'
                f'<span>{e(costo_corto(h))} · {e(DISPONIBLE.get(h["route"].get("availability"), ("", ""))[0])}</span></a>'
                for h in hermanos)
            otros = (f'<aside class="otros"><p><b>Hay {len(hermanos) + 1} caminos para lo mismo.</b> Este es '
                     f'«{e(d["route"]["name"])}».</p><div class="caminos">{chips}</div>'
                     f'<a class="comparar" href="{e(x["base"])}/{e(meta["id"])}">Compara los {len(hermanos) + 1} caminos</a></aside>')
    desc = corta(d.get("summary", ""), 180)
    rep = {
        "TITULO": e(d["title"]), "DESC": e(desc), "URL": e(x["url"]), "OG": e(x["url"] + "/og.png"),
        "LUGAR": e(lugar), "TIPO": "Trámite" if d["kind"] == "tramite" else "Por dentro del gobierno",
        "RESUMEN": e(d.get("summary", "")), "HECHOS": hechos, "NCOLS": str(max(1, len(x["hechos"]) - 1)), "PASOS": "".join(pasos), "MAPA": mapa(x["pasos"]),
        "REQS": "".join(reqs), "OFIS": ofis, "GLOS": glos, "FUENTES": "".join(fuentes), "BASE": base_legal,
        "ESTADO": e(estado), "REVISADO": e(fecha(d["last_checked"])), "ARCHIVO": e(archivo), "ID": e(d["id"]),
        "WA": e("https://wa.me/?text=" + urllib.parse.quote(x["wa"])), "CAMINOS": otros,
    }
    out = TPL
    for k, v in rep.items():
        out = out.replace("{{" + k + "}}", v)
    # quita las secciones vacías
    for sec, val in (("reqs", reqs), ("ofis", ofis), ("glos", glos), ("hechos", hechos), ("pasos", pasos)):
        if not val:
            out = re.sub(rf"<!--{sec}-->.*?<!--/{sec}-->", "", out, flags=re.S)
    return out


def whatsapp(d, x):
    lineas = [f"*{d['title']}*", f"_{LUGAR.get(d['jurisdiction'], d['jurisdiction'])} · Compartido · Por dentro_", ""]
    if x["cost"].get("text"):
        lineas += [f"💲 {x['cost']['text']}"]
    if "vigencia" in x["dls"]:
        lineas += [f"⏳ {corta(x['dls']['vigencia']['text'], 160)}"]
    lineas += ["", "*La ruta*"]
    for p in x["pasos"]:
        quien = "" if es_tu(p["actor"]) else f"{p['actor']}: "
        lineas.append(f"{p['n']}. {quien}{corta(p['action'], 120)}")
    reqs = d.get("requirements", [])
    if reqs:
        lineas += ["", "*Lleva esto*"] + [f"• {corta(r['text'], 90)}" for r in reqs]
    lineas += ["", f"Cada paso con su fuente oficial: {x['url']}"]
    return "\n".join(lineas)


def imagen_html(d, x, tipo):
    """HTML de una sola pantalla para og.png o ruta.png."""
    lugar = LUGAR.get(d["jurisdiction"], d["jurisdiction"])
    costo = x["hechos"][0][1] if x["hechos"] and x["hechos"][0][0] == "Cuesta" else ""
    datos_ = " · ".join(v for v in (f"{len(x['pasos'])} pasos" if x["pasos"] else "", f"Cuesta {costo}" if costo else "", "Cada paso con su fuente") if v)
    if tipo == "og":
        cadena = "".join(f'<li class="{"tu" if es_tu(p["actor"]) else ""}">{e(p["n"])}</li>' for p in x["pasos"][:10])
        cuerpo = (f'<div class="og"><header class="img-top">{LOGO}<span class="marca">compartido</span><span class="pill">Por dentro</span></header>'
                  f'<div class="og-cuerpo"><div><p class="lugar">{e(lugar)}</p><h1>{e(d["title"])}</h1><p class="datos">{e(datos_)}</p></div>'
                  f'<ol class="cadena">{cadena}</ol></div><div class="hilos"></div></div>')
    else:
        caja = "".join(f'<div><small>{e(k)}</small><b>{e(v)}</b></div>' for k, v, _ in x["hechos"] if k != "Pasos")
        caja = f'<div class="caja-datos">{caja}</div>' if caja else ""
        densa = ""
        cuerpo = (f'<div class="ruta{densa}"><header class="img-top">{LOGO}<span class="marca">compartido</span><span class="pill">Por dentro</span></header>'
                  f'<p class="lugar">{e(lugar)}</p><h1>{e(d["title"])}</h1>{mapa(x["pasos"], grande=True)}'
                  f'{caja}<footer><span>Cada paso con su fuente oficial en</span><b>{e(x["url"].split("://")[-1])}</b></footer><div class="hilos"></div></div>')
    css = re.search(r"<style>(.*?)</style>", TPL, re.S)[1]
    fuentes = re.search(r'(<link rel="preconnect".*?display=swap" rel="stylesheet">)', TPL, re.S)[1]
    js = re.search(r'(<script id="dibujar-flechas">.*?</script>)', TPL, re.S)[1]
    return f'<!doctype html><html lang="es-MX"><head><meta charset="utf-8">{fuentes}<style>{css}</style></head><body class="lienzo">{cuerpo}{js}</body></html>'


def meta_datos(meta, base):
    """Datos para la página que compara los caminos hacia una misma meta."""
    rutas = []
    orden, srcs = [], {}
    for d, f in caminos(meta["id"]):
        r = d["route"]

        def chips(cites, d=d):
            out = []
            for c in cites:
                clave = (d["id"], c["source"])
                if clave not in orden:
                    orden.append(clave)
                    srcs[clave] = d["sources"].get(c["source"], {})
                tip = " · ".join(v for v in (c.get("pinpoint"), c.get("quote")) if v)
                out.append(f'<a class="cita" href="#f{orden.index(clave) + 1}" title="{e(tip)}">{orden.index(clave) + 1}</a>')
            return "".join(out)

        disp, color = DISPONIBLE.get(r.get("availability"), ("", "anil"))
        rutas.append(dict(
            d=d, nombre=r["name"], disp=disp, color=color, disp_txt=r.get("availability_text", ""),
            costo=costo_corto(d), costo_txt=(d.get("cost") or {}).get("text", ""),
            docs=len(d.get("requirements", [])), pasos=len(d.get("steps", [])),
            pros=[(n["text"], chips(n["cites"])) for n in r.get("pros", [])],
            cons=[(n["text"], chips(n["cites"])) for n in r.get("cons", [])],
            url=f"{base}/{ruta_corta(d)}", borrador=d["status"] == "borrador"))
    return rutas, orden, srcs


def pagina_meta(meta, base):
    rutas, orden, srcs = meta_datos(meta, base)
    url = f"{base}/{meta['id']}"
    tarjetas = []
    for r in rutas:
        pros = "".join(f"<li>{e(t)} {c}</li>" for t, c in r["pros"])
        cons = "".join(f"<li>{e(t)} {c}</li>" for t, c in r["cons"])
        cuando = f'<p class="cuando">{e(r["disp_txt"])}</p>' if r["disp_txt"] else ""
        tarjetas.append(
            f'<article class="opcion"><header><h3>{e(r["nombre"])}</h3>'
            f'<span class="disp disp--{r["color"]}">{e(r["disp"])}</span></header>'
            f'<dl class="cifras"><div><dt>Cuesta</dt><dd>{e(r["costo"])}</dd></div><div><dt>Documentos</dt><dd>{r["docs"]}</dd></div>'
            f'<div><dt>Pasos</dt><dd>{r["pasos"]}</dd></div></dl>'
            f'{cuando}'
            f'{f"<h4>Elige este si</h4><ul class=pros>{pros}</ul>" if pros else ""}'
            f'{f"<h4>Antes de ir</h4><ul class=cons>{cons}</ul>" if cons else ""}'
            f'<a class="boton boton--ver" href="{e(r["url"])}">Ver el camino paso a paso</a></article>')
    fuentes = []
    for i, k in enumerate(orden):
        s_ = srcs[k]
        tipo = TIPO_FUENTE.get(s_.get("type"), s_.get("type", ""))
        of = "oficial" if s_.get("official", True) else "no oficial"
        pub = f'<small>{e(s_["publisher"])}</small>' if s_.get("publisher") else ""
        t = f'<a href="{e(s_["url"])}" rel="noopener">{e(s_.get("title", k[1]))}</a>' if s_.get("url") else e(s_.get("title", k[1]))
        fuentes.append(f'<li id="f{i + 1}"><span class="tipo tipo--{"of" if s_.get("official", True) else "no"}">{e(tipo)} · {of}</span>{t}'
                       f'{pub}</li>')
    wa = "\n".join([f"*{meta['title']}*", "_Compartido · Por dentro_", "", f"Hay {len(rutas)} caminos:"]
                   + [f"• *{r['nombre']}*: {r['costo']}, {r['docs']} documentos. {r['disp']}." for r in rutas]
                   + ["", f"Compáralos, con sus fuentes oficiales: {url}"])
    principal = (
        f'<main><div class="cabeza"><p class="lugar">Una meta, {len(rutas)} caminos</p><h1>{e(meta["title"])}</h1>'
        f'<p class="resumen">Hay varias formas de lograrlo, en lugares distintos. Cambian el costo, los papeles y cuándo se pueden hacer.</p>'
        f'<div class="hilos" aria-hidden="true"></div></div>'
        f'<div class="opciones">{"".join(tarjetas)}</div>'
        f'<div class="compartir"><a class="boton boton--wa" href="{e("https://wa.me/?text=" + urllib.parse.quote(wa))}" target="_blank" rel="noopener">Mandar por WhatsApp</a>'
        f'<button class="boton" type="button" id="copiar">Copiar enlace</button></div><p class="aviso" id="aviso" role="status"></p>'
        f'<section aria-labelledby="t-fuentes"><h2 id="t-fuentes">Fuentes</h2><ol class="fuentes">{"".join(fuentes)}</ol></section>'
        f'</main>')
    out = re.sub(r"<main>.*?</main>", lambda m: principal, TPL, flags=re.S).replace('class="envoltura"', 'class="envoltura envoltura--ancha"')
    desc = f"Hay {len(rutas)} caminos: " + "; ".join(f"{r['nombre']} ({r['costo']})" for r in rutas) + "."
    for k, v in {"TITULO": e(meta["title"]), "DESC": e(desc), "URL": e(url), "OG": e(url + "/og.png"), "ID": e(meta["id"])}.items():
        out = out.replace("{{" + k + "}}", v)
    out = out.replace(": la ruta paso a paso, con fuentes oficiales", ": los caminos, comparados")
    return out, rutas, wa


def imagen_meta(meta, rutas, base):
    filas = "".join(
        f'<li><div><b>{e(r["nombre"])}</b><span class="disp disp--{r["color"]}">{e(r["disp"])}</span></div>'
        f'<strong>{e(r["costo"])}</strong><small>{r["docs"]} documentos</small></li>' for r in rutas)
    cuerpo = (f'<div class="og og--meta"><header class="img-top">{LOGO}<span class="marca">compartido</span><span class="pill">Por dentro</span></header>'
              f'<p class="lugar">Una meta, {len(rutas)} caminos</p><h1>{e(meta["title"])}</h1><ol class="comparo">{filas}</ol>'
              f'<div class="hilos"></div></div>')
    css = re.search(r"<style>(.*?)</style>", TPL, re.S)[1]
    fuentes = re.search(r'(<link rel="preconnect".*?display=swap" rel="stylesheet">)', TPL, re.S)[1]
    return f'<!doctype html><html lang="es-MX"><head><meta charset="utf-8">{fuentes}<style>{css}</style></head><body class="lienzo">{cuerpo}</body></html>'


# Si el contenido no cabe en la imagen, achica la lista (o el título) hasta que quepa.
AJUSTAR = """() => {
  const caja = document.querySelector('.og, .ruta');
  const el = document.querySelector('.ruta .mapa') || document.querySelector('.og h1');
  const pie = document.querySelector('.ruta footer, .og .datos');
  const nocabe = () => {
    const r = el.getBoundingClientRect(), p = pie.getBoundingClientRect();
    return caja.scrollHeight > innerHeight || p.bottom > innerHeight - 40 || (el.classList.contains('mapa') && r.bottom > p.top - 8);
  };
  let z = 1;
  while (nocabe() && z > 0.5) { z -= 0.03; el.style.zoom = z; }
  if (window.dibujarFlechas) window.dibujarFlechas();
}"""

LOGO = ('<svg class="logo" viewBox="0 0 120 120" aria-hidden="true"><path d="M79.3 37A30 30 0 1 0 79.3 83" fill="none" '
        'stroke="currentColor" stroke-width="14" stroke-linecap="round"/><circle cx="45.2" cy="105.7" r="9" fill="var(--jade)"/>'
        '<circle cx="21.2" cy="88.2" r="9" fill="var(--anil)"/><circle cx="12" cy="60" r="9" fill="var(--cemp-logo)"/>'
        '<circle cx="21.2" cy="31.8" r="9" fill="var(--jaca)"/><circle cx="45.2" cy="14.3" r="9" fill="var(--barro)"/></svg>')
TPL = TPL.replace("{{LOGO}}", LOGO)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--todas", action="store_true")
    ap.add_argument("--salida", default=str(R / "salida/dentro"))
    ap.add_argument("--base", default="https://compartido.org/dentro")
    ap.add_argument("--sin-imagenes", action="store_true")
    a = ap.parse_args()
    ids = a.ids
    if a.todas:
        ids = [yaml.safe_load(f.read_text())["id"] for f in sorted((R / "procedimientos").rglob("*.yaml"))
               if yaml.safe_load(f.read_text()).get("steps")]
    if not ids:
        ap.error("di al menos un id o usa --todas")

    navegador = None
    if not a.sin_imagenes:
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            ruta_chromium = os.environ.get("CHROMIUM")  # opcional: ruta a un Chromium ya instalado
            navegador = pw.chromium.launch(executable_path=ruta_chromium) if ruta_chromium else pw.chromium.launch()
        except Exception as err:  # noqa: BLE001
            print(f"Sin imágenes: Playwright no está disponible ({err.__class__.__name__}).")

    metas = {}
    for pid in ids:
        d, f = cargar(pid)
        x = datos(d, a.base)
        x["ruta_archivo"] = str(f.relative_to(R))
        x["wa"] = whatsapp(d, x)
        html_ = pagina(d, x)
        out = Path(a.salida) / ruta_corta(d)
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(html_, encoding="utf-8")
        (out / "whatsapp.txt").write_text(x["wa"] + "\n", encoding="utf-8")
        if navegador:
            for tipo, (w, h) in (("og", (1200, 630)), ("ruta", (1080, 1350))):
                pg = navegador.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
                pg.set_content(imagen_html(d, x, tipo), wait_until="networkidle")
                pg.evaluate("document.fonts.ready")
                pg.evaluate(AJUSTAR)
                pg.screenshot(path=str(out / f"{tipo}.png"))
                pg.close()
        print(out)
        if d.get("goal"):
            metas[d["goal"]["id"]] = d["goal"]
    for meta in metas.values():
        html_, rutas, wa = pagina_meta(meta, a.base.rstrip("/"))
        out = Path(a.salida) / meta["id"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(html_, encoding="utf-8")
        (out / "whatsapp.txt").write_text(wa + "\n", encoding="utf-8")
        if navegador:
            pg = navegador.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
            pg.set_content(imagen_meta(meta, rutas, a.base), wait_until="networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=str(out / "og.png"))
            pg.close()
        print(out)
    if navegador:
        navegador.close()


if __name__ == "__main__":
    main()
