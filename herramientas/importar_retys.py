#!/usr/bin/env python3
"""Importa el Registro Estatal de Trámites y Servicios de Baja California (RETyS).

RETyS no ofrece descarga masiva, pero su buscador usa un JSON público:
  https://retys.bajacalifornia.gob.mx/api/Tramites/get?search=%20   (lista completa)
y cada ficha se publica en HTML en /Portal/TyS/<Id>.

Uso:  python3 importar_retys.py <carpeta-salida-yaml> <carpeta-html-crudo>
Guarda el HTML crudo (para poder auditar el import) y un YAML por trámite con status: importado.
"""
import datetime, html, json, re, sys, time, unicodedata, urllib.request
from pathlib import Path
from bs4 import BeautifulSoup
import yaml

BASE = "https://retys.bajacalifornia.gob.mx"
HOY = datetime.date.today().isoformat()
UA = {"User-Agent": "catalogo-compartido/0.1 (importador de datos abiertos)"}


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def slug(s, n=60):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:n].rstrip("-")


def txt(el):
    if el is None:
        return ""
    for a in el.find_all("a"):
        a.decompose()
    return re.sub(r"\s+", " ", el.get_text(" ")).strip()


def campo(soup, etiqueta):
    for b in soup.select(".contenido-tramite b"):
        if b.get_text(strip=True).upper().startswith(etiqueta):
            div = b.parent
            t = re.sub(r"\s+", " ", div.get_text(" ")).strip()
            return t.split(":", 1)[1].strip() if ":" in t else ""
    return None


def si_no(v):
    if v is None:
        return None
    return v.strip().lower().startswith("s")


def costo(soup):
    for b in soup.select(".contenido-tramite b"):
        k = b.get_text(strip=True).upper()
        if k.startswith("COSTO") or k.startswith("GRATUITO") or k.startswith("SIN COSTO"):
            t = re.sub(r"\s+", " ", b.parent.get_text(" ")).strip()
            tipo = "variable" if "VARIABLE" in k else ("gratuito" if ("GRATUITO" in k or "SIN COSTO" in k) else "fijo")
            m = re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", t)
            amt = float(m[0].replace(",", "")) if len(m) == 1 else None
            if amt == 0:
                tipo = "gratuito"
            return {"type": tipo, "amount_mxn": amt, "text": t, "as_of": HOY,
                    "cites": [{"source": "retys"}]}
    return {"type": "desconocido", "amount_mxn": None, "text": "La ficha no publica costo.", "as_of": HOY,
            "cites": [{"source": "retys"}]}


def parse(tid, page, meta):
    s = BeautifulSoup(page, "html.parser")
    titulo = txt(s.select_one(".titulo")) or meta.get("NombreCiudadano") or meta["NombreOficial"]
    hc = s.select_one(".homoclave")
    homoclave = re.sub(r"(?i)homoclave:\s*", "", txt(hc)) if hc else None
    actualizado = txt(s.select_one(".fecha-tramite")).replace("Actualizado el", "").strip()
    canales = []
    for p in s.select(".pills"):
        t = p.get_text(strip=True).lower()
        canales.append("en_linea" if "línea" in t or "linea" in t else "presencial")

    sources = {"retys": {
        "type": "registro_oficial", "official": True,
        "title": f"RETyS, ficha {tid}: {titulo}",
        "publisher": "Gobierno del Estado de Baja California",
        "url": f"{BASE}/Portal/TyS/{tid}",
        "version_date": actualizado or None,
        "accessed": HOY}}
    sources["retys"] = {k: v for k, v in sources["retys"].items() if v}

    legal = []
    fund = s.select_one("#fundamento")
    if fund:
        for i, li in enumerate(fund.select("li"), 1):
            b = li.find("b")
            ley = txt(b) if b else txt(li)
            pin = re.sub(r"\s+", " ", li.get_text(" ")).replace(ley, "", 1).strip() if b else ""
            key = f"ley{i}"
            sources[key] = {"type": "reglamento" if ley.lower().startswith("reglamento") else "ley",
                            "official": True, "title": ley,
                            "publisher": "citado por RETyS (falta enlazar el texto oficial)"}
            c = {"source": key}
            if pin:
                c["pinpoint"] = pin
            legal.append(c)

    plazos = []
    pl = s.select_one("#plazos")
    if pl:
        for li in pl.select("li"):
            t = re.sub(r"\s+", " ", li.get_text(" ")).strip()
            what = "respuesta_autoridad" if "resolver" in t.lower() else (
                "para_prevenir" if "prevenir" in t.lower() else (
                "para_corregir" if "subsanar" in t.lower() or "cumplir" in t.lower() else "otro"))
            plazos.append({"what": what, "text": t, "cites": [{"source": "retys"}]})
    vig = campo(s, "VIGENCIA")
    if vig:
        plazos.append({"what": "vigencia", "text": vig, "cites": [{"source": "retys"}]})

    escenarios, pasos_planos = [], []
    for esc in s.select(".cont-tab-escenario"):
        eid = esc.get("id", "").replace("escenario-", "")
        tab = s.select_one(f'.tab-escenario[data-id="{eid}"]')
        nombre = txt(tab) if tab else "General"
        notas = ""
        first = []
        for node in esc.children:
            if getattr(node, "name", None) == "b":
                break
            first.append(node.get_text(" ") if hasattr(node, "get_text") else str(node))
        notas = re.sub(r"\s+", " ", " ".join(first)).strip()
        reqs = []
        for li in esc.select("li.marker-pequeño"):
            a = li.find("a", href=True)
            r = {"text": txt(BeautifulSoup(str(li), "html.parser")), "cites": [{"source": "retys"}]}
            if a and a["href"].startswith("/"):
                r["form_url"] = BASE + a["href"]
            reqs.append(r)
        modos = []
        for mod in esc.select(".cont-tab-modalidad"):
            mid = mod.get("id", "").split("-")[1]
            mt = s.select_one(f'.tab-modalidad[data-id="{mid}"]')
            pasos = [txt(li) for li in mod.select("li")]
            modos.append({"name": txt(mt) if mt else "", "steps": pasos})
        e = {"name": nombre, "requirements": reqs, "modes": modos}
        if notas:
            e["notes"] = notas
        escenarios.append(e)
        if not pasos_planos and modos and modos[0]["steps"]:
            pasos_planos = modos[0]["steps"]

    oficinas = []
    of = s.select_one("#oficinas")
    if of:
        for co in of.select(".cont-tab-oficina"):
            oid = co.get("id", "").replace("oficina-", "")
            mt = of.select_one(f'.tab-oficina[data-id="{oid}"]')
            muni = txt(mt) if mt else ""
            for card in co.select(".carta-oficina"):
                nb = card.find("b")
                lines = [l.strip() for l in card.get_text("\n").split("\n") if l.strip()]
                o = {"municipality": muni, "name": nb.get_text(" ", strip=True) if nb else ""}
                if len(lines) > 1:
                    o["address"] = lines[1]
                modal = card.find_next("div", class_=re.compile("modal"))
                oficinas.append(o)
            if not co.select(".carta-oficina"):
                pass
    # Datos de contacto de oficinas: solo nombre y dirección. No guardamos nombres ni correos de servidores públicos.

    steps = []
    for i, p in enumerate(pasos_planos, 1):
        steps.append({"n": str(i), "actor": "tú (según RETyS)", "action": p, "cites": [{"source": "retys"}]})

    org = meta.get("Organismo") or txt(s.select_one(".subtitulo"))
    doc = {
        "id": f"mx-bcn-retys-{tid}-{slug(titulo, 50)}",
        "country": "MX",
        "jurisdiction": "MX-BCN",
        "inegi_code": "02",
        "level": "estatal",
        "branch": "ejecutivo",
        "kind": "tramite",
        "category": "",
        "title": titulo,
        "summary": re.sub(r"\s+", " ", meta.get("Descripcion") or "").strip(),
        "authority": {"name": org.strip()},
        "official_ids": {"retys_id": int(tid), "retys_url": f"{BASE}/Portal/TyS/{tid}"},
        "who_can": [x.strip() for x in (campo(s, "QUIEN PUEDE") or "").split(",") if x.strip()],
        "when": campo(s, "CUANDO REALIZARLO") or "",
        "result": campo(s, "QUE SE OBTIENE") or "",
        "cost": costo(s),
        "deadlines": plazos,
        "positive_silence": si_no(campo(s, "AFIRMATIVA FICTA")),
        "requires_inspection": si_no(campo(s, "REQUIERE INSPECCI")),
        "channels": sorted(set(canales)),
        "offices": oficinas,
        "scenarios": escenarios,
        "legal_basis": legal,
        "steps": steps,
        "sources": sources,
        "status": "importado",
        "last_checked": HOY,
        "checked_by": "importar_retys.py",
        "notes": "Copiado tal cual de RETyS. Los pasos son los del primer escenario y la primera modalidad; las demás variantes están en scenarios. Las leyes citadas aún no enlazan a su texto oficial.",
    }
    if homoclave:
        doc["official_ids"]["homoclave"] = homoclave
    if meta.get("NombreOficial") and meta["NombreOficial"].strip() != titulo:
        doc["notes"] = f"Nombre oficial: {meta['NombreOficial'].strip()}. " + doc["notes"]
    # quita vacíos
    return {k: v for k, v in doc.items() if v not in ("", [], None) or k in ("positive_silence", "requires_inspection", "steps")}


def main():
    out, raw = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True); raw.mkdir(parents=True, exist_ok=True)
    lista_p = raw / "lista.json"
    if not lista_p.exists():
        lista_p.write_text(get(f"{BASE}/api/Tramites/get?search=%20"), encoding="utf-8")
    datos = json.loads(lista_p.read_text(encoding="utf-8"))["Datos"]
    ok = err = 0
    for m in datos:
        tid = m["Id"]
        hp = raw / f"{tid}.html"
        try:
            if not hp.exists():
                hp.write_text(get(f"{BASE}/Portal/TyS/{tid}"), encoding="utf-8")
                time.sleep(0.4)
            doc = parse(tid, hp.read_text(encoding="utf-8"), m)
            (out / f"{doc['id']}.yaml").write_text(
                yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
            ok += 1
        except Exception as e:
            err += 1
            print("ERROR", tid, repr(e)[:200], file=sys.stderr)
    print(f"importados {ok}, errores {err}")


if __name__ == "__main__":
    main()
