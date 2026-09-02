# Estado del proyecto

Fecha de publicación: **2026-09-02**. Versión: **0.1.0 alpha**.

Repositorio: [Jsantiagom11/gmail_surgical_purge](https://github.com/Jsantiagom11/gmail_surgical_purge), rama `main`.

## Terminado y verificado

- Publicados los 47 archivos revisados, sin credenciales ni datos de un buzón real.
- Importación inicial: `756399b7004c3a631f57e96e575a3fbb5d6e5857`.
- El árbol publicado coincide con el snapshot local recuperado `b46088e`.
- CLI modular, aprobación explícita, protecciones por mensaje, lotes y reanudación.
- Guía en las dos fases solicitadas: [RUNBOOK_ES.md](docs/RUNBOOK_ES.md).
- 116 pruebas locales sin red; cobertura de 99,42 %, lint, tipado estricto y paquete instalable.
- GitHub Actions pasó en Python 3.11, 3.12 y 3.13 para la importación inicial.
  [Ejecución verificada](https://github.com/Jsantiagom11/gmail_surgical_purge/actions/runs/33643832025).

## Pendiente

1. Decidir licencia antes de promoverlo como software de código abierto.
2. Ejecutar un piloto real de archivado, pequeño y revisado, solo con autorización.
3. Revisar políticas de conservación y copias de seguridad antes de usar Papelera.

La publicación y las pruebas no certifican uso en producción. No se ejecutaron
operaciones sobre Gmail al preparar o publicar este repositorio.

## Continuar desde GitHub

```bash
git clone https://github.com/Jsantiagom11/gmail_surgical_purge.git
cd gmail_surgical_purge
uv sync --locked --dev
bash scripts/check.sh
```

El bundle `gmail-surgical-purge.bundle` conserva el snapshot local previo a la
publicación. Es una copia de recuperación, no sustituye a la versión actual de
`main`; la importación de GitHub tiene otro commit, con el mismo árbol de archivos.

Consulta [evidencia](docs/EVIDENCE.md), [mantenimiento](docs/PUBLISHING.md) y los
[resultados actuales de CI](https://github.com/Jsantiagom11/gmail_surgical_purge/actions/workflows/ci.yml).
