# Using Por dentro from another project or agent

This page is for people and AI agents who want to **use** the catalog in their own project, ask how it works, or request changes. If you want to **contribute** content, read [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md) instead.

*Español: esta guía explica cómo usar el catálogo desde otro proyecto y cómo hacernos preguntas. Las preguntas se pueden escribir en español o en inglés.*

## What it is

"Compartido · Por dentro" is an open catalog of how Mexico's government works, step by step, with a source for every step. It has two kinds of entries (`kind`):

- **Trámites**: what a person asks the government for (register a birth, get a license). Requirements, cost, deadlines, office and legal basis.
- **Internal procedures**: how government works inside (how a law is passed, how spending is approved and audited, what happens to a complaint against an official).

Today it covers federal Mexico (`MX`), Baja California (`MX-BCN`) and Tijuana (`MX-BCN-Tijuana`). Code is MIT; content is CC BY-SA 4.0 (credit "Compartido · Por dentro" and share alike).

## How to read the data

Everything is plain files in this repository. No API key, no login.

- One YAML file per procedure under `procedimientos/<jurisdiction>/...`. Clone the repo, or read a file at `https://raw.githubusercontent.com/Revoluciones/catalogo-gobierno/main/<path>`.
- `esquema/procedimiento.schema.json` defines every field. Read it before you parse files. Required fields: `id`, `country`, `jurisdiction`, `level`, `kind`, `title`, `summary`, `authority`, `steps`, `sources`, `status`, `last_checked`.
- `glosario.yaml` explains each legal term once in everyday words; a procedure links terms by key in `glossary`.
- `reportes/<procedure-id>/` holds reports of how a procedure really went (schema in `esquema/reporte.schema.json`). They never change the official version.
- `herramientas/validar.py` checks every file against the schema. `herramientas/pagina.py` builds the browsable page.
- A good example to start from: `procedimientos/MX/federal/internos/mx-como-se-aprueba-una-ley-federal.yaml`.

Keys are in English. All human-readable text is in Mexican Spanish (es-MX).

## What you can rely on

- **Every step cites a source** (law and article, official manual, official register or portal, transparency answer, audit, court ruling or news report). If a fact had no source we could open, the field is left out rather than guessed.
- **Law and practice are separate.** A step says what the official source says. What actually happens goes in `practice`, with its own sources and an `evidence_level`.
- **`status` tells you how far to trust a file:**
  - `importado`: copied from an official register without edits (errors in the register stay; corrections go in issues).
  - `borrador`: written from the cited sources; nobody else has checked it yet.
  - `revisado`: a second person checked every step against its source.
  - `desactualizado`: the source changed and the file did not.
- `last_checked` is the date someone last compared the file with its sources.

## How we work

1. Work starts from an issue. A maintainer labels it `disponible`; a contributor comments `/tomar` to claim it (a bot assigns it and adds `en-curso`).
2. One issue per pull request. The PR says `Cierra #<n>`, passes `validar` (`0 errores`) and fills "Uso de IA".
3. A person on the Revoluciones team reviews and merges every PR. Schema changes (`esquema/`) are discussed in an issue first.
4. No personal data anywhere, and no opinions about parties, politicians or governments.

## Ask a question or request a change

Open an issue with the **"Pregunta o pedido (otro proyecto o agente)"** template. It adds the `pregunta` label. The Por dentro maintainers, including their AI assistant, check these issues several times a day and answer in the issue. Keep the conversation in the same issue: reply there with follow-ups.

- **Questions:** how a field works, where data comes from, whether a procedure exists, how to use the data in your project.
- **Requests:** a new field, an export format, a jurisdiction, a fix. If a request is accepted, a maintainer links the issue or pull request that does it, so you can follow it.
- **Errors in a specific file:** you can also use the "Corregir" template.

Please say who is asking (project name, and whether you are an AI agent acting for someone), what you need, and why. Do not post personal data, credentials or anything behind a login. To report personal data or a security problem, use the private link in [SECURITY.md](SECURITY.md).

If you are an AI agent: you can read everything here on your own. Opening an issue needs a GitHub account, so ask your human to open it if you cannot. Then check the issue for answers; there is no need for your human to copy messages back and forth.
