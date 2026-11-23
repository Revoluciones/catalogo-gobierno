#!/usr/bin/env python3
"""Dibuja un procedimiento como diagrama de flujo BPMN 2.0.

Uso: python3 herramientas/exportar_bpmn.py <archivo.yaml> [salida.bpmn]

Usa el núcleo de procedimientos (procedures_core.py), el mismo que dibuja los procedimientos de Barda:
inicio, paso, decisión, otro procedimiento y fin. El diagrama abre en bpmn.io y en Barda.
"""
import sys
from pathlib import Path

import yaml

import procedures_core as core

R = Path(__file__).resolve().parent.parent


def diagrama(d, titulos=None):
    """El BPMN de una ficha ya leída, revisado. titulos: {id: título} de los procedimientos a los que apunta."""
    titulos = dict(titulos or {})
    pasos = [dict(s) for s in d["steps"]]
    numeros = {str(s["n"]) for s in pasos}
    for s in pasos:
        s["n"] = str(s["n"])
        ramas = s.get("next") or []
        if len(ramas) > 1:  # una decisión necesita todas sus respuestas con nombre
            s["ask"] = "¿Qué pasa después?"
            juntas = {}  # varias razones para llegar al mismo paso son una sola flecha
            for r in ramas:
                juntas.setdefault(str(r["to"]), []).append(core.short(r.get("when") or "Sigue", 34))
            s["next"] = ramas = [{"to": to, "when": " / ".join(razones)} for to, razones in juntas.items()]
            if len(ramas) == 1:
                s.pop("ask")
                ramas[0].pop("when")
        for r in ramas:
            if str(r["to"]) not in numeros and r["to"] not in core.ENDS:
                titulos.setdefault(r["to"], r["to"])
    cuando = d.get("when")
    proc = {"title": d["title"], "steps": pasos, "result": d.get("result") or "Fin",
            "starts_when": core.short(cuando, 80) if isinstance(cuando, str) and cuando else "Inicio"}
    xml = core.to_bpmn(proc, titulos)
    core.check_diagram(xml, titulos.values(), d["title"])
    return xml


def titulos_del_catalogo():
    return {f.stem: " ".join(yaml.safe_load(f.read_text())["title"].split()) for f in (R / "procedimientos").rglob("*.yaml")}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    origen = Path(sys.argv[1])
    d = yaml.safe_load(origen.read_text())
    relacionados = {i: t for i, t in titulos_del_catalogo().items() if i in str(d.get("steps"))}
    try:
        xml = diagrama(d, relacionados)
    except core.ValidationError as error:
        sys.exit("No se pudo dibujar:\n- " + "\n- ".join(error.messages))
    salida = Path(sys.argv[2]) if len(sys.argv) > 2 else origen.with_suffix(".bpmn")
    salida.write_text(xml, encoding="utf-8")
    print(salida)
