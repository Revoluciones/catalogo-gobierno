# Reportes: cómo te fue de verdad

Cada reporte vive en `reportes/<id-del-procedimiento>/<fecha>-<6 letras>.yaml` y sigue `esquema/reporte.schema.json`.
Nunca se edita la versión oficial con un reporte. Cuando varios reportes coinciden, alguien escribe una nota
`practice` en el paso correspondiente, con una fuente de tipo `reportes_ciudadanos` que lista los `report_ids`.

Antes de publicar: se tapan nombres, CURP, firmas, caras, placas y domicilios en toda evidencia (`redacted: true`),
y el reporte pasa de `pendiente` a `publicado` solo después de revisarlo.

Este folder `_ejemplo` es de demostración y no cuenta para nada.
