#!/usr/bin/env python3
"""Importa el Registro Municipal de Trámites y Servicios de Tijuana (REMUTyS, remutys.tijuana.gob.mx).

El sitio es una app de React Router. Cada lista y cada ficha también se sirve como datos en formato
turbo-stream añadiendo ".data" a la ruta:
  /tramites.data?fetchMode=pagination&page=N&pageSize=15   (y /tramites/servicios.data, /tramites/apoyos.data)
  /<HOMOCLAVE>.data                                         (ficha completa)
Este script toma las fichas ya decodificadas a JSON (decodificar con el paquete npm turbo-stream, ver
decodificar_turbo_stream.mjs) y escribe un YAML por trámite.

Uso: python3 importar_remutys.py <carpeta-json> <salida-tijuana> <salida-para-barda>
"""
import datetime, glob, json, re, sys, unicodedata
from pathlib import Path
import yaml

BASE = "https://remutys.tijuana.gob.mx"
HOY = datetime.date.today().isoformat()
# Trámites de propiedad: se quedan en Barda.
PROPIEDAD = re.compile(r"(?i)construcci|uso de suelo|predi|catastr|fraccion|demolici|alineamiento|n[uú]mero oficial|"
                       r"traslaci[oó]n de dominio|adquisici[oó]n de inmuebles|ISAI|deslinde|subdivisi|fusi[oó]n de|"
                       r"condominio|terminaci[oó]n de obra|aval[uú]o|lotific|relotific|regularizaci[oó]n de lote|"
                       r"bard[ae]|edificaci|ocupaci[oó]n de obra")
KIND = {"TRAMITE": "trámite", "SERVICIO": "servicio", "PROGRAMA_APOYO_SOCIAL": "programa de apoyo"}


def slug(s, n=50):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:n].rstrip("-")


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def mxn(x, uma, valor):
    return round(x * valor, 2) if uma else x


def build(data):
    q, uma = data["procedure"], (data.get("uma") or {}).get("valor")
    hc = q["homoclave"]
    url = f"{BASE}/{hc}"
    sources = {"remutys": {"type": "registro_oficial", "official": True,
                           "title": f"REMUTyS Tijuana, ficha {hc}: {clean(q['nombre'])}",
                           "publisher": "XXV Ayuntamiento de Tijuana",
                           "url": url, "version_date": (q.get("fechaActualizacion") or "")[:10], "accessed": HOY}}
    legal = []
    for i, f in enumerate(q.get("fundamentos") or [], 1):
        k = f"fund{i}"
        nombre = clean(f["nombre"])
        sources[k] = {"type": "reglamento" if "eglamento" in nombre else "ley", "official": True, "title": nombre}
        if f.get("documentoUrl"):
            sources[k]["url"] = f["documentoUrl"]
        legal.append({"source": k})

    reqs = []
    for r in q.get("tramiteRequisitos") or []:
        t = clean(r["requisito"]["nombre"])
        if r.get("comentario"):
            t += f". {clean(r['comentario'])}"
        req = {"text": t, "cites": [{"source": "remutys"}]}
        oc = []
        if r.get("original"):
            oc.append("original")
        if r.get("copias"):
            oc.append(f"{r['copias']} copia(s)")
        if oc:
            req["original_or_copy"] = ", ".join(oc)
        reqs.append(req)

    costos = q.get("tramiteCostos") or []
    if q.get("gratis") or (costos and all(not c["costo"] for c in costos)):
        cost = {"type": "gratuito", "amount_mxn": 0, "text": "Gratuito según la ficha oficial."}
    elif costos:
        partes = []
        for c in costos:
            v = c["costo"]
            if c.get("uma") and uma:
                partes.append(f"{clean(c['concepto']['nombre'])}: {v:g} UMA (${mxn(v, True, uma):,.2f})")
            else:
                partes.append(f"{clean(c['concepto']['nombre'])}: ${v:,.2f}")
        un = len(costos) == 1
        cost = {"type": "fijo" if un else "variable",
                "amount_mxn": mxn(costos[0]["costo"], costos[0].get("uma"), uma or 0) if un else None,
                "text": " · ".join(partes) + (f". UMA 2026 = ${uma}." if uma and any(c.get("uma") for c in costos) else "")}
    else:
        cost = {"type": "desconocido", "amount_mxn": None, "text": "La ficha no publica costo."}
    cost.update({"as_of": HOY, "cites": [{"source": "remutys"}]})

    plazos = []
    if q.get("tiempoDeResolucion"):
        med = (q.get("tiempoResolucionMedida") or {}).get("nombre", "")
        plazos.append({"what": "respuesta_autoridad", "text": f"{q['tiempoDeResolucion']} {med}".strip(),
                       "cites": [{"source": "remutys"}]})
    vm = (q.get("vigenciaMedida") or {}).get("nombre", "")
    if q.get("vigencia") or (vm and vm != "Sin vigencia"):
        plazos.append({"what": "vigencia", "text": f"{q.get('vigencia') or ''} {vm}".strip(), "cites": [{"source": "remutys"}]})

    canales = []
    for m in q.get("modalidades") or []:
        n = m["nombre"].lower()
        canales.append("en_linea" if "línea" in n or "linea" in n else ("telefono" if "tel" in n else "presencial"))

    oficinas = [{"municipality": "Tijuana", "name": clean(o.get("nombre")), "address": clean(o.get("direccion")),
                 "phones": clean(f"{o.get('telefono') or ''} ext. {o['extension']}" if o.get("extension") else o.get("telefono")),
                 "hours": clean(o.get("horario"))} for o in q.get("oficinas") or []]
    oficinas = [{k: v for k, v in o.items() if v} for o in oficinas]

    titulo = clean(q["nombre"]).rstrip(".")
    doc = {
        "id": f"mx-bcn-tijuana-{hc.lower()}-{slug(titulo)}",
        "country": "MX", "jurisdiction": "MX-BCN-Tijuana", "inegi_code": "02004", "level": "municipal",
        "branch": "ejecutivo", "kind": "tramite",
        "category": ", ".join(t["nombre"] for t in q.get("temas") or []) or KIND.get(q.get("tipo"), ""),
        "title": titulo,
        "summary": clean(q.get("descripcion")),
        "authority": {"name": clean(q["dependencia"]["nombre"]) + " (Ayuntamiento de Tijuana)",
                      "unit": clean((q.get("departamento") or {}).get("nombre"))},
        "official_ids": {"homoclave": hc},
        "who_can": [w.capitalize() for w in q.get("quienPuedeRealizarlo") or [] if w != "OTRO"],
        "when": " · ".join(clean(c["nombre"]) for c in q.get("cuandosRealizar") or []),
        "result": clean((q.get("entregable") or {}).get("nombre")),
        "requirements": reqs, "cost": cost, "deadlines": plazos,
        "positive_silence": q.get("afirmativaFicta"),
        "requires_inspection": q.get("requiereInspeccionMunicipal"),
        "channels": sorted(set(canales)), "offices": oficinas,
        "legal_basis": legal,
        "steps": [],
        "sources": sources, "status": "importado", "last_checked": HOY, "checked_by": "importar_remutys.py",
        "notes": "Copiado de REMUTyS (registro municipal de Tijuana). El registro no publica pasos; los requisitos sí."
                 + (f" Tipo en el registro: {KIND.get(q.get('tipo'), q.get('tipo'))}." if q.get("tipo") != "TRAMITE" else "")
                 + (f" Para empezar: {q['linkParaIniciarTramite']}" if q.get("linkParaIniciarTramite") else "")
                 + (f" Criterio para resolver: {clean(q['criterioDeResolucion'])}" if q.get("criterioDeResolucion") else ""),
    }
    if not doc["authority"]["unit"]:
        del doc["authority"]["unit"]
    return {k: v for k, v in doc.items() if v not in ("", [], None) or k in ("steps", "positive_silence", "requires_inspection")}


def main():
    src, out, barda = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True); barda.mkdir(parents=True, exist_ok=True)
    n = b = 0
    for f in sorted(src.glob("*.json")):
        d = json.loads(f.read_text())
        data = next(v for k, v in d.items() if "procedure-key" in k)["data"]
        doc = build(data)
        to = barda if PROPIEDAD.search(doc["title"]) else out
        b += to is barda; n += to is out
        (to / f"{doc['id']}.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    print(f"Tijuana: {n} al catálogo, {b} de propiedad para Barda")


if __name__ == "__main__":
    main()
