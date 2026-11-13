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
import argparse, html, os, re, sys, urllib.parse
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
    return dict(src=src, orden=orden, num=num, chips=chips, cost=cost, dls=dls, pasos=pasos, hechos=hechos, url=url)


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

    desc = corta(d.get("summary", ""), 180)
    rep = {
        "TITULO": e(d["title"]), "DESC": e(desc), "URL": e(x["url"]), "OG": e(x["url"] + "/og.png"),
        "LUGAR": e(lugar), "TIPO": "Trámite" if d["kind"] == "tramite" else "Por dentro del gobierno",
        "RESUMEN": e(d.get("summary", "")), "HECHOS": hechos, "NCOLS": str(max(1, len(x["hechos"]) - 1)), "PASOS": "".join(pasos),
        "REQS": "".join(reqs), "OFIS": ofis, "GLOS": glos, "FUENTES": "".join(fuentes), "BASE": base_legal,
        "ESTADO": e(estado), "REVISADO": e(fecha(d["last_checked"])), "ARCHIVO": e(archivo), "ID": e(d["id"]),
        "WA": e("https://wa.me/?text=" + urllib.parse.quote(x["wa"])),
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
        pasos = "".join(
            f'<li class="{"tu" if es_tu(p["actor"]) else ""}"><span class="n">{e(p["n"])}</span><div><small>{e(p["actor"])}</small>'
            f'<p>{e(corta(p["action"], 105))}</p>'
            + "".join(f'<p class="prac">En la práctica: {e(corta(q["text"], 95))}</p>' for q in p.get("practice", [])[:1])
            + '</div></li>' for p in x["pasos"][:12])
        if len(x["pasos"]) > 12:
            pasos += f'<li class="mas"><span class="n">+{len(x["pasos"]) - 12}</span><div><p>pasos más en la ficha completa</p></div></li>'
        densa = " densa" if len(x["pasos"]) > 8 else ""
        cuerpo = (f'<div class="ruta{densa}"><header class="img-top">{LOGO}<span class="marca">compartido</span><span class="pill">Por dentro</span></header>'
                  f'<p class="lugar">{e(lugar)}</p><h1>{e(d["title"])}</h1><ol>{pasos}</ol>'
                  f'{caja}<footer><span>Cada paso con su fuente oficial en</span><b>{e(x["url"].split("://")[-1])}</b></footer><div class="hilos"></div></div>')
    css = re.search(r"<style>(.*?)</style>", TPL, re.S)[1]
    fuentes = re.search(r'(<link rel="preconnect".*?display=swap" rel="stylesheet">)', TPL, re.S)[1]
    return f'<!doctype html><html lang="es-MX"><head><meta charset="utf-8">{fuentes}<style>{css}</style></head><body class="lienzo">{cuerpo}</body></html>'


# Si el contenido no cabe en la imagen, achica la lista (o el título) hasta que quepa.
AJUSTAR = """() => {
  const caja = document.querySelector('.og, .ruta');
  const el = document.querySelector('.ruta ol') || document.querySelector('.og h1');
  const pie = document.querySelector('.ruta footer, .og .datos');
  const nocabe = () => {
    const r = el.getBoundingClientRect(), p = pie.getBoundingClientRect();
    return caja.scrollHeight > innerHeight || p.bottom > innerHeight - 40 || (el.tagName === 'OL' && r.top + el.scrollHeight * (parseFloat(el.style.zoom) || 1) > p.top - 8);
  };
  let z = 1;
  while (nocabe() && z > 0.5) { z -= 0.03; el.style.zoom = z; }
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
    if navegador:
        navegador.close()


if __name__ == "__main__":
    main()
