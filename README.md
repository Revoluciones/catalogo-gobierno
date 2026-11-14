# Cómo funciona el gobierno de México, paso a paso

Un catálogo abierto de procedimientos del gobierno mexicano. Hay dos tipos:

- **Trámites**: lo que una persona le pide al gobierno (registrar un nacimiento, sacar una licencia, presentar una denuncia). Cada uno trae requisitos, costo, plazos, oficina y fundamento legal.
- **Procedimientos internos**: cómo trabaja el gobierno por dentro (cómo se aprueba una ley, cómo se decide y se revisa el gasto, qué pasa con una denuncia contra un servidor público).

Hoy cubre México (federal), Baja California y Tijuana. El país es un campo de cada ficha (`country`), para sumar otros países de América Latina después.

## Tres reglas

1. **Cada paso cita su fuente**: la ley y el artículo, un manual de organización o de procedimientos, un registro o portal oficial, o una respuesta a una solicitud de transparencia.
2. **Ley y práctica, por separado**: el paso dice lo que manda la fuente oficial. Si en la práctica pasa otra cosa, va en `practice`, con sus propias fuentes y el nivel de evidencia (sentencia, auditoría, periodismo, varios reportes).
3. **Lo que vive la gente no toca la versión oficial**: los reportes van en `reportes/` con su evidencia, sin datos personales, y se revisan antes de publicarse.

## Carpetas

| Carpeta | Qué hay |
| --- | --- |
| `procedimientos/MX/federal/` | Procedimientos federales escritos a partir de la ley |
| `procedimientos/MX-BCN/tramites/` | Los trámites del Registro Estatal de Trámites y Servicios de Baja California (RETyS), importados tal cual |
| `procedimientos/MX-BCN-Tijuana/tramites/` | Los trámites, servicios y apoyos del registro municipal de Tijuana (REMUTyS), importados tal cual |
| `procedimientos/MX-BCN-Tijuana/guias/` | Rutas completas que juntan varios trámites oficiales, de principio a fin, con su práctica aparte |
| `para-barda/` | Trámites de propiedad (Registro Público, gravámenes, predial, permisos de construcción); viven en Barda |
| `reportes/` | Reportes de cómo fue un trámite de verdad |
| `esquema/` | Las reglas de cada ficha (JSON Schema) |
| `glosario.yaml` | Cada término legal explicado una vez, en palabras de todos los días |
| `herramientas/` | `importar_retys.py` y `importar_remutys.py` (vuelven a bajar los registros estatal y de Tijuana) `validar.py` (revisa todo) y `ficha.py` (la ficha para compartir de un procedimiento: página, vista previa para WhatsApp, imagen de la ruta y mensaje listo para pegar) |
| `fuentes-crudas.tar.gz` | Copias de las páginas oficiales tal como se bajaron, para poder auditar el import (`tar xzf fuentes-crudas.tar.gz`) |

Los códigos de lugar son los mismos que usa Barda: `MX`, `MX-BCN`, `MX-BCN-Tijuana`.

## Revisar

```
pip install -r requirements.txt
python3 herramientas/validar.py
```

## Estado de cada ficha

- `importado`: copiado de un registro oficial sin cambios.
- `borrador`: escrito por el proyecto a partir de las fuentes citadas; falta que otra persona lo coteje.
- `revisado`: alguien cotejó cada paso con su fuente.
- `desactualizado`: la fuente cambió y la ficha no.

## Contribuir

Este catálogo lo construimos entre muchas personas de todo México, con o sin agentes de IA. Para no hacer el mismo trabajo dos veces, cada tarea se aparta antes de empezar:

1. Escoge un [issue `disponible`](../../issues?q=is%3Aopen+label%3Adisponible) (o `para-empezar` si es tu primera vez).
2. Comenta `/tomar`. La tarea queda a tu nombre.
3. Abre un pull request con `Cierra #<número>`.

Los detalles están en [CONTRIBUTING.md](CONTRIBUTING.md). Si usas Claude Code, Codex, Cursor, Copilot u otro agente, ya lee solo [AGENTS.md](AGENTS.md).

## Licencia

El código usa la licencia [MIT](LICENSE). El contenido usa [CC BY-SA 4.0](LICENSE-DATOS.md): puedes usarlo y cambiarlo si das crédito y compartes igual.

Lo mantiene [Revoluciones](https://compartido.org) como parte de Compartido.
