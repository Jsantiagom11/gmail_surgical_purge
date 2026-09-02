# Estado recuperable del proyecto

Fecha: **2026-09-02**. Versión: **0.1.0 alpha**.

## Terminado

- CLI Python modular: configurar, autorizar, auditar, planificar, revisar, aplicar,
  consultar estado y ejecutar una demo sin Gmail.
- Protección por mensaje, aprobación explícita, cuentas separadas de demo/producción,
  lotes acotados y checkpoints para reanudación.
- Guía en las dos fases solicitadas: [RUNBOOK_ES.md](docs/RUNBOOK_ES.md).
- Pruebas sin red, tipado estricto, controles de publicación y CI configurada.
- Código público de ejemplo separado de cualquier material personalizado del buzón.

## Pendiente y fuera de las afirmaciones de esta versión

1. Crear o seleccionar un repositorio GitHub vacío y verificar su URL.
2. Publicar el commit local sin sobrescribir historial ajeno.
3. Comprobar los tres trabajos de GitHub Actions tras el push.
4. Decidir licencia antes de promoverlo como software de código abierto.
5. Hacer un piloto de archivado real, pequeño y revisado, solo con autorización.

No se han ejecutado operaciones sobre Gmail durante la preparación de este
repositorio. No se afirma que esté publicado, certificado o probado en producción.

## Recuperar el código y el historial

Con el archivo `gmail-surgical-purge.bundle` en el directorio actual:

```bash
git clone gmail-surgical-purge.bundle gmail-surgical-purge
cd gmail-surgical-purge
git log -1 --oneline
uv sync --locked --dev
bash scripts/check.sh
```

El ZIP de código sirve para inspeccionar o descargar los archivos; el bundle
conserva también la rama y el historial Git. No contiene credenciales ni datos de
un buzón real.

Consulta [evidencia de verificación](docs/EVIDENCE.md) y
[pasos de publicación](docs/PUBLISHING.md). Para retomar, parte de esta versión;
no copies material personalizado a este repositorio.
