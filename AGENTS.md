# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor, Copilot, Gemini and others) and the people who run them. `CLAUDE.md` imports this file. `CONTRIBUTING.md` says the same things for people, in Spanish.

## The five rules (CI checks the first four)

1. **Work only on a claimed issue.** Before you write anything, find an issue labeled `disponible` and ask your human to comment `/tomar` on it. Do not start on an issue that already has an assignee or the `en-curso` label: someone else is doing it. If no issue fits, open one with a template and wait for a maintainer to label it `disponible`. A PR whose body does not say `Cierra #<n>` for an issue assigned to the PR author fails the `vinculado` check.
2. **One issue per PR, small diffs.** Do not fix unrelated things, reformat files you did not need to touch, or re-run an importer over the whole registry unless the issue asks for it.
3. **Run the validator and paste its last line in the PR.** `python3 herramientas/validar.py` must end with `0 errores`. The `validar` check runs it again.
4. **Disclose AI use.** Fill the "Uso de IA" section of the PR template: which tool and model, and what a human checked by hand. The `vinculado` check fails if that section is empty.
5. **Never invent a source.** Every step, requirement, cost and deadline cites a source you actually opened: a law and article, an official manual, an official register or portal, a transparency request answer, an audit, a court ruling or a news report. If you cannot open the source, leave the field out and say so in the PR. A missing fact is fine; a made-up one gets the PR closed.

## Setup

```bash
pip install -r requirements.txt
python3 herramientas/validar.py      # must print "... 0 errores"
```

A dev container (`.devcontainer/`) does the same in Codespaces.

## Repository map

| Path | What it is |
| --- | --- |
| `procedimientos/<jurisdiction>/...` | One YAML file per procedure. Jurisdiction codes: `MX`, `MX-BCN`, `MX-BCN-Tijuana`; new states use ISO 3166-2 (`MX-JAL`), municipalities `MX-JAL-Guadalajara`. |
| `esquema/procedimiento.schema.json` | The rules every procedure file must meet. Read it before writing a file. |
| `esquema/reporte.schema.json` | The rules for lived-experience reports. |
| `glosario.yaml` | Each legal term explained once in everyday words. A procedure links terms by key in `glossary`. |
| `reportes/<procedure-id>/` | Reports of how a procedure really went. Never put personal data here. |
| `herramientas/` | Importers (`importar_*.py`), the validator, the page builder. |
| `fuentes-crudas.tar.gz` | Raw copies of official pages as downloaded, so imports can be audited. Unpack with `tar xzf fuentes-crudas.tar.gz` (the folder is gitignored). |

Keys are in English. All human-readable content is in Mexican Spanish (es-MX).

## How to write content

- **Law and practice stay separate.** A step says what the official source says. If practice differs, put it in `practice` with its own sources and an `evidence_level`. Never mix the two in one sentence.
- **Plain language.** Write for someone with no legal training. Explain each legal term once in `glosario.yaml` and link it; write percentages as "1 de cada N".
- **Neutral.** No opinions about parties, politicians or governments. Describe what the rule says and what sources show happens.
- **Copy official registers exactly.** Imported files (`status: importado`) are copied from the register without edits. Corrections go in a new field or a `borrador` file that cites the register, never by editing the imported text.
- **Status.** New hand-written files start as `borrador`. Only a second person who checked every step against its source may set `revisado`.
- **Find an example first.** Copy the shape of a similar file, for example `procedimientos/MX/federal/internos/mx-como-se-aprueba-una-ley-federal.yaml`.

## Importers and government servers

- Keep at most 1 request per second to any government server, and cache raw responses in `fuentes-crudas/`. Say in the PR that the archive needs regenerating; a maintainer rebuilds `fuentes-crudas.tar.gz`.
- Use a generic User-Agent (`catalogo-gobierno-importer`); never put a personal name or email in it.
- An importer must be re-runnable and produce the same files from the same raw data.
- Do not commit credentials, cookies or anything behind a login.

## Never

- Commit personal data (names, CURP, RFC, phone numbers, addresses, photos of IDs), even in `reportes/` or `fuentes-crudas/`.
- Change `esquema/` without an issue that asks for it; every file depends on it.
- Push to `main`, force-push someone else's branch, or close other people's issues and PRs.
- Open a PR for an issue you were not assigned, or several PRs for the same issue.
- Add legal advice, disclaimers or political opinions.

## When you are stuck

Comment on the issue with what you tried and what is blocking you, then stop. A maintainer will answer. Asking is better than guessing.
