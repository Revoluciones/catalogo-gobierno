#!/usr/bin/env python3
"""Genera una página HTML navegable con todo el catálogo. Uso: python3 herramientas/pagina.py salida.html"""
import json, sys
from pathlib import Path
import yaml

R = Path(__file__).resolve().parent.parent
glos = yaml.safe_load((R / "glosario.yaml").read_text())
items = []
for f in sorted((R / "procedimientos").rglob("*.yaml")):
    d = yaml.safe_load(f.read_text())
    src = d.get("sources", {})
    def cite(c):
        s = src.get(c["source"], {})
        return {"t": s.get("title", c["source"]), "u": s.get("url", ""), "p": c.get("pinpoint", ""),
                "o": bool(s.get("official", True)), "k": s.get("type", "")}
    steps = []
    for s in d.get("steps", []):
        steps.append({"n": s["n"], "a": s.get("actor", ""), "x": s["action"], "d": s.get("deadline", ""),
                      "c": [cite(c) for c in s.get("cites", [])],
                      "nx": [{"to": n["to"], "w": n.get("when", "")} for n in s.get("next", [])],
                      "pr": [{"x": p["text"], "e": p["evidence_level"], "o": p.get("observed", ""),
                              "c": [cite(c) for c in p["cites"]]} for p in s.get("practice", [])]})
    scen = []
    for e in d.get("scenarios", []):
        scen.append({"n": e["name"], "no": e.get("notes", ""), "r": [r["text"] for r in e.get("requirements", [])],
                     "m": [{"n": m.get("name", ""), "s": m.get("steps", [])} for m in e.get("modes", [])]})
    items.append({
        "id": d["id"], "k": d["kind"], "j": d["jurisdiction"], "lv": d["level"], "cat": d.get("category", ""),
        "t": d["title"], "s": d.get("summary", ""), "au": d["authority"]["name"],
        "hc": d.get("official_ids", {}).get("homoclave", ""), "ru": d.get("official_ids", {}).get("retys_url") or src.get("remutys", {}).get("url", ""),
        "who": d.get("who_can", []), "rq": [r["text"] + (f" ({r['original_or_copy']})" if r.get("original_or_copy") else "") for r in d.get("requirements", [])], "res": d.get("result", ""),
        "cost": (d.get("cost") or {}).get("text", ""), "ct": (d.get("cost") or {}).get("type", ""),
        "dl": [x["text"] for x in d.get("deadlines", [])],
        "pf": d.get("positive_silence"),
        "ch": d.get("channels", []),
        "of": [" · ".join(v for v in (o.get("municipality"), o.get("name"), o.get("address")) if v) for o in d.get("offices", [])],
        "lb": [cite(c) for c in d.get("legal_basis", [])],
        "st": steps, "sc": scen, "g": {k: glos[k] for k in d.get("glossary", []) if k in glos},
        "rel": d.get("related", []), "stt": d["status"], "lc": d["last_checked"], "no": d.get("notes", ""),
    })
data = json.dumps(items, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
tpl = (R / "herramientas/pagina.plantilla.html").read_text()
Path(sys.argv[1]).write_text(tpl.replace("/*DATOS*/[]", data), encoding="utf-8")
print(len(items), "fichas,", len(data) // 1024, "KB de datos")
