# Cómo contribuir

Gracias por ayudar. Este catálogo explica cómo funciona el gobierno de México, paso a paso y con fuentes. Lo mantiene [Revoluciones](https://compartido.org) como parte de Compartido, y lo construimos entre todas y todos.

*English: contributions are welcome in English too; content files stay in Mexican Spanish. AI agents: read [AGENTS.md](AGENTS.md).*

## En 4 pasos

1. **Escoge una tarea.** Ve a [Issues](../../issues?q=is%3Aopen+label%3Adisponible) y busca las que dicen `disponible`. Si eres nuevo, empieza por `para-empezar`.
2. **Apártala.** Escribe `/tomar` en un comentario. Un bot te la asigna y le pone `en-curso`, así nadie más la empieza. Puedes tener hasta 2 tareas a la vez. Si ya no puedes seguir, escribe `/soltar`.
3. **Haz el cambio** y revisa que todo pase:
   ```bash
   pip install -r requirements.txt
   python3 herramientas/validar.py   # tiene que decir "0 errores"
   ```
4. **Abre un pull request** con `Cierra #<número>` y llena la plantilla.

¿No hay tarea para lo que quieres hacer? Abre un issue con una de las plantillas y espera a que alguien del equipo le ponga `disponible`. Así evitamos que 10 personas hagan lo mismo.

## Por qué apartamos tareas

Con agentes de IA es muy fácil que muchas personas resuelvan el mismo issue al mismo tiempo y que casi todo ese trabajo se tire. Por eso:

- Solo se acepta un pull request por issue, del autor asignado. Una revisión automática (`vinculado`) lo comprueba.
- Si una tarea `en-curso` pasa 14 días sin movimiento, el bot avisa y a los 7 días siguientes la vuelve a dejar `disponible`.
- ¿Quieres ayudar en una tarea que ya tiene a alguien? Comenta en el issue y pónganse de acuerdo. Trabajar juntos está bien; empezar en paralelo sin decir nada, no.

## Si usas un agente de IA

Bienvenido. Nosotros también los usamos. Solo te pedimos:

- Que tu agente lea [AGENTS.md](AGENTS.md). Claude Code, Codex, Cursor, Copilot y Gemini lo leen solos si abres el repositorio.
- Que tú apartes la tarea y abras el pull request. Tú respondes por lo que se manda.
- Que digas en la plantilla qué herramienta y modelo usaste, y qué revisaste tú a mano.
- Que revises cada fuente: los agentes a veces inventan artículos de ley o direcciones de oficinas. Una ficha con una fuente inventada se cierra.

## Reglas del contenido

1. **Cada paso cita su fuente**: la ley y el artículo, un manual, un registro o portal oficial, una respuesta de transparencia, una auditoría, una sentencia o una nota de prensa.
2. **Ley y práctica, por separado.** El paso dice lo que manda la fuente oficial. Si en la práctica pasa otra cosa, va en `practice`, con sus propias fuentes.
3. **Palabras de todos los días.** Escribe para alguien que nunca estudió derecho. Cada término legal se explica una vez en `glosario.yaml`. Los porcentajes van como "1 de cada N".
4. **Neutral.** Sin opiniones sobre partidos, políticos ni gobiernos.
5. **Sin datos personales.** Nada de nombres, CURP, RFC, teléfonos, domicilios ni fotos de identificaciones, ni siquiera en `reportes/`.
6. **Lo importado se copia tal cual.** Si un registro oficial tiene un error, no lo corrijas en la ficha importada: abre un issue de corrección.

## Qué puedes aportar

| Tarea | Etiqueta |
| --- | --- |
| Importar el registro de trámites de otro estado o municipio | `importar` |
| Escribir un procedimiento interno (cómo se aprueba un presupuesto estatal, cómo se nombra a un juez…) | `procedimiento` |
| Cotejar una ficha `borrador` contra sus fuentes y pasarla a `revisado` | `cotejar` |
| Corregir algo que está mal o desactualizado | `corregir` |
| Herramientas: el validador, la página, exportar a otros formatos | `herramientas` |

## Quién decide

- Revoluciones mantiene el repositorio. Cada pull request necesita la aprobación de una persona del equipo para entrar.
- Los cambios al esquema (`esquema/`) se platican primero en un issue, porque todas las fichas dependen de él.
- Quien aporte seguido y bien puede sumarse al equipo de revisión. Pídelo en un issue.

## Licencia de lo que aportas

Al mandar un pull request aceptas que tu aporte se publique con las licencias del proyecto: el código bajo [MIT](LICENSE) y el contenido bajo [CC BY-SA 4.0](LICENSE-DATOS.md). No pedimos firmar nada más.

## Trato

Seguimos el [Código de conducta](CODE_OF_CONDUCT.md). Si ves datos personales o un problema de seguridad, avisa como dice [SECURITY.md](SECURITY.md), no en un issue público.
