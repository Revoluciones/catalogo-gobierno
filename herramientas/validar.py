#!/usr/bin/env python3
"""Valida todos los procedimientos y reportes contra su esquema y revisa que cada cita apunte a una fuente.

Uso: python3 herramientas/validar.py   (desde la raíz del catálogo)
"""
import json, sys
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator

R = Path(__file__).resolve().parent.parent
proc = Draft202012Validator(json.loads((R / "esquema/procedimiento.schema.json").read_text()))
rep = Draft202012Validator(json.loads((R / "esquema/reporte.schema.json").read_text()))
glos = yaml.safe_load((R / "glosario.yaml").read_text())
errores, ids = [], set()


def citas(doc):
    def walk(x):
        if isinstance(x, dict):
            if "source" in x and isinstance(x["source"], str) and set(x) <= {"source", "pinpoint", "quote"}:
                yield x["source"]
            for v in x.values():
                yield from walk(v)
        elif isinstance(x, list):
            for v in x:
                yield from walk(v)
    yield from walk({k: v for k, v in doc.items() if k != "sources"})


for f in sorted((R / "procedimientos").rglob("*.yaml")):
    d = yaml.safe_load(f.read_text())
    for e in proc.iter_errors(d):
        errores.append(f"{f.relative_to(R)}: {'/'.join(map(str, e.path))}: {e.message[:160]}")
    if d.get("id") in ids:
        errores.append(f"{f.relative_to(R)}: id repetido {d['id']}")
    ids.add(d.get("id"))
    for c in citas(d):
        if c not in d.get("sources", {}):
            errores.append(f"{f.relative_to(R)}: cita a una fuente que no existe: {c}")
    for g in d.get("glossary", []):
        if g not in glos:
            errores.append(f"{f.relative_to(R)}: término sin definir en glosario.yaml: {g}")

for f in sorted((R / "reportes").rglob("*.yaml")):
    d = yaml.safe_load(f.read_text())
    for e in rep.iter_errors(d):
        errores.append(f"{f.relative_to(R)}: {'/'.join(map(str, e.path))}: {e.message[:160]}")
    if d.get("procedure_id") not in ids:
        errores.append(f"{f.relative_to(R)}: el procedimiento {d.get('procedure_id')} no existe")
    if any(not ev.get("redacted") for ev in d.get("evidence", [])) and d.get("review", {}).get("state") == "publicado":
        errores.append(f"{f.relative_to(R)}: evidencia publicada sin tapar datos personales")

print(f"{len(ids)} procedimientos revisados, {len(errores)} errores")
for e in errores[:200]:
    print(" -", e)
sys.exit(1 if errores else 0)
