# Guía operativa: Gmail Surgical Purge

## FASE 1: PURGA Quirúrgica y Descongestionamiento (0 a 140k+)

### 1. Proteger primero; buscar después

- **No existe una purga sin margen de error.** Categoría, edad o palabras no demuestran que un mensaje sea prescindible. Ante duda: archivar.
- **Archivar descongestiona Inbox; no libera almacenamiento.** Mover a Papelera tampoco equivale a un borrado permanente inmediato.
- Exporta lo irremplazable con [Google Takeout](https://takeout.google.com/), espera a que termine y comprueba que puedes abrir mensajes del archivo. Nunca publiques el MBOX.
- Crea las cinco etiquetas de Fase 2. Protege documentación y mensajes personales antes de seleccionar basura. No deduzcas obligaciones de conservación por antigüedad.
- Configura remitentes excluidos y etiquetas protegidas en `config.local.toml`. Las subetiquetas requieren protección explícita: la jerarquía no es herencia.
- Si operas desde la web, desactiva temporalmente la vista por conversaciones y revisa la selección. Un hilo puede contener mensajes que no coinciden todos con la búsqueda. El CLI trabaja con IDs individuales.

**Barrera común.** Añádela al final de cada consulta manual de candidatos:

```text
-is:starred -is:important -in:sent -in:drafts -in:trash -in:spam -label:01_ACTION -label:02_WAITING -label:03_RECORDS -label:04_KNOWLEDGE
```

El CLI añade las exclusiones para las etiquetas configuradas que existen. No sabe qué contenido tiene valor si no lo has protegido.

**Consultas para revisar.** Las direcciones `example.com` son ficticias: sustitúyelas por remitentes concretos validados. Todas requieren la barrera anterior; ninguna autoriza borrado por sí sola.

| Objetivo | Consulta base | Destino inicial |
|---|---|---|
| Promociones antiguas | `category:promotions older_than:1y -has:attachment` | Revisar; archivar si hay duda |
| Boletín conocido | `from:newsletter@example.com older_than:1y {unsubscribe "darse de baja"} -has:attachment` | Papelera solo tras validar la lista |
| Notificaciones sociales | `category:social older_than:180d from:notifications@example.com -has:attachment` | Revisar y archivar |
| Resultado de sistema obsoleto | `from:ci@example.com older_than:180d subject:"build succeeded" -has:attachment` | Revisar y depurar |
| Confirmaciones caducadas | `from:events@example.com older_than:2y subject:"registration confirmed" -has:attachment` | Revisar; excluir pagos, garantías y reservas activas |
| Lista identificada | `list:weekly.example.com older_than:1y` | Revisar la lista exacta |
| Archivo promocional | `label:99_ARCHIVE older_than:2y category:promotions -has:attachment` | Revisar; archivar de nuevo no reduce nada |
| Mensajes grandes | `size:10000000 older_than:2y has:attachment` | Inspección individual, no purga automática |
| Adjuntos muy grandes | `larger:20M older_than:1y has:attachment -filename:pdf` | Revisar; excluir PDF no garantiza seguridad |
| Inbox antiguo | `in:inbox older_than:30d` | Archivar lo resuelto |

Ejemplo completo, sin concatenación pendiente:

```text
category:promotions older_than:1y -has:attachment -is:starred -is:important -in:sent -in:drafts -in:trash -in:spam -label:01_ACTION -label:02_WAITING -label:03_RECORDS -label:04_KNOWLEDGE
```

`unsubscribe` es texto libre, no un detector fiable de la cabecera `List-Unsubscribe`. `size:` usa bytes; `older_than:` admite `d`, `m` y `y`. No uses `from:noreply` como criterio universal: también envía documentos y alertas. [Sintaxis oficial](https://support.google.com/mail/answer/7190).

### 2. Ejecución por lotes: selección estable y alcance acotado

**Web: un operador y una sola pestaña de limpieza.** Los tamaños siguientes son una política conservadora del proyecto, no límites oficiales.

1. Elige categoría y remitente; procesa del periodo más antiguo al más nuevo.
2. Congela una ventana. Ejemplo:

   ```text
   category:promotions after:2024/01/01 before:2024/02/01 -has:attachment -is:starred -is:important -in:sent -in:drafts -in:trash -in:spam -label:01_ACTION -label:02_WAITING -label:03_RECORDS -label:04_KNOWLEDGE
   ```

3. Si el resultado es amplio, divide el mes en semanas y después días. No supongas que las fechas de Gmail usan tu zona horaria: revisa los límites; para API puedes usar segundos Unix. [Diferencias API/web](https://developers.google.com/workspace/gmail/api/guides/filtering).
4. Piloto: revisa 50-100 mensajes completos. Si aparece uno crítico, detén el lote y corrige la regla. Una muestra posterior no sustituye este piloto.
5. Comienza con una página seleccionada. Solo tras comprobar el alcance utiliza «seleccionar todas las conversaciones que coinciden» para esa ventana acotada.
6. Escala a 500-1.000 candidatos por ventana si la interfaz responde. Ejecuta una acción y espera la confirmación de Gmail; no selecciones los 140.000 de golpe.
7. Repite la búsqueda y registra consulta, ventana, acción y resultado localmente. Para archivar, añade `in:inbox` para excluir lo ya archivado.
8. Si hay latencia o resultado incierto, no repitas clics: recarga y comprueba Inbox/Papelera. Reduce el siguiente lote a la mitad.

**API:** el programa termina de paginar la búsqueda antes de escribir, guarda IDs exactos y deduplica reglas. Cada mensaje pertenece a la primera regla coincidente. No modifica resultados mientras recorre páginas. Escribe 250 IDs por defecto, hasta el máximo de 1.000 admitido por [batchModify](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/batchModify).

### 3. Matriz de decisión: tres acciones

| Acción | Condición | Ejecución |
|---|---|---|
| **Eliminar definitivamente** | Basura inequívoca, selección revisada y ninguna conservación pendiente | Primero Papelera; revisar allí mensajes concretos antes del borrado definitivo manual. El CLI no ofrece borrado permanente. |
| **Archivar para búsqueda futura** | Resuelto, informativo, documental o dudoso; sin acción inmediata | Quitar Inbox y conservar etiquetas. Sigue localizable y ocupando espacio. |
| **Conservar en Inbox** | Acción propia, alerta relevante o decisión de hoy | Añadir `01_ACTION`; resolver, delegar o fijar seguimiento. |

No vacíes toda la Papelera para terminar un lote: puede contener mensajes ajenos a la purga. Gmail normalmente elimina su contenido después de 30 días; revísalo antes. El programa no garantiza recuperación ni liberación instantánea de espacio. [Borrado y recuperación](https://support.google.com/mail/answer/7401).

### 4. Motor Python: plan, aprobación y reanudación

Requisitos: Linux/WSL2, Python 3.11+ y [uv](https://docs.astral.sh/uv/getting-started/installation/). Código modular en `src/gmail_surgical_purge/`. Es una **alpha verificada con pruebas sintéticas**, no un servicio certificado ni probado aquí sobre un buzón real.

**Instalar y ensayar sin Gmail:**

```bash
uv sync --locked --dev
uv run --frozen gmail-purge demo --messages 12000
cp config/rules.example.toml config.local.toml
uv run --frozen gmail-purge config-check --config config.local.toml
```

La demo procesa 12.000 candidatos sintéticos sin red. Para repetirla usa otro directorio con `--output`; su plan no puede aplicarse a Gmail.

**Configurar y autorizar lectura:**

1. Edita `config.local.toml`: acota por remitente/fechas el piloto. Mantén archivado como acción inicial; Papelera viene desactivada.
2. Crea un proyecto Google propio, habilita Gmail API y genera un cliente OAuth Desktop con la [guía oficial](https://developers.google.com/workspace/gmail/api/quickstart/python).
3. Guarda el JSON como `.gmail-purge/client.json`. Nunca lo subas a GitHub.
4. Autoriza lectura, verifica la cuenta y genera un plan pequeño:

   ```bash
   uv run --frozen gmail-purge auth --credentials .gmail-purge/client.json
   uv run --frozen gmail-purge audit
   uv run --frozen gmail-purge plan --config config.local.toml --output .gmail-purge/pilot-plan.json --max-messages 100 --sample-size 20
   uv run --frozen gmail-purge review --plan .gmail-purge/pilot-plan.json --show-samples
   ```

El máximo es un **freno**, no un truncamiento: si coinciden más de 100 candidatos, no se guarda un plan parcial. Reduce el alcance. Revisa todos los candidatos del piloto en Gmail, además de las muestras del plan.

**Autorizar escritura y aplicar ese plan:**

```bash
uv run --frozen gmail-purge auth --credentials .gmail-purge/client.json --write
uv run --frozen gmail-purge apply --plan .gmail-purge/pilot-plan.json --confirm APPLY-TOKEN_DEL_PLAN
uv run --frozen gmail-purge status --plan .gmail-purge/pilot-plan.json
```

Sustituye `APPLY-TOKEN_DEL_PLAN` por el token de `review`. Un plan con Papelera también exige `--allow-trash`; no agregues esa opción por costumbre.

**Escalar después del piloto:**

```bash
uv run --frozen gmail-purge plan --config config.local.toml --output .gmail-purge/lote-01.json --max-messages 20000 --sample-size 20
uv run --frozen gmail-purge review --plan .gmail-purge/lote-01.json --show-samples
uv run --frozen gmail-purge apply --plan .gmail-purge/lote-01.json --confirm APPLY-TOKEN_DEL_LOTE --quiet
uv run --frozen gmail-purge status --plan .gmail-purge/lote-01.json
```

El límite admite hasta 1.000.000 de candidatos, con memoria O(N). No implica ejecución inmediata: 140.000 lecturas de metadatos a 20 solicitudes/s suponen aproximadamente 117 minutos de presupuesto ideal de solicitudes, antes de red, búsquedas, escrituras y reintentos. **No es una medición de rendimiento real.**

| Situación | Respuesta |
|---|---|
| Interrupción o cierre de terminal | Repetir el mismo `apply`, token y ruta de estado; conservar el checkpoint |
| 429, 5xx o límite transitorio admitido | Reintentos limitados; si se agotan, revisar y reanudar |
| Autorización/política denegada | Detenerse y corregir por los canales normales |
| Plan vencido | Revisar progreso y generar uno nuevo; caducidad por defecto: 24 horas |
| Mensaje protegido desde la planificación | Omitir al revisar sus etiquetas antes del lote |
| Reducir salida | `--quiet` oculta progreso, no fallos ni el resumen final |

No se garantiza ejecución silenciosa e ininterrumpida. No programes un cron que genere y apruebe nuevos planes destructivos. Equipo despierto y sesión persistente ayudan, pero no resuelven cuotas, OAuth ni red. Lee [limitaciones y recuperación](SAFETY.md) antes del uso real.

## FASE 2: Arquitectura Post-Purga ("Sistema Navaja Suiza")

### 1. Ingesta automática: filtros y alias

Filtros, colores y plantillas se configuran **manualmente en Gmail**. El CLI no instala filtros, envía respuestas ni cancela suscripciones.

1. Gmail web → Configuración → Ver todos los ajustes → Filtros y direcciones bloqueadas → Crear un filtro.
2. Pega una consulta en «Contiene las palabras» y usa Buscar para validar ejemplos.
3. Crea las acciones indicadas abajo, inicialmente solo para mensajes futuros. No apliques a conversaciones existentes sin revisar ese alcance aparte.
4. Durante una semana revisa diariamente los destinos. Exporta los filtros antes de cambios importantes. [Administración de filtros](https://support.google.com/mail/answer/6579).

Sustituye los ejemplos por direcciones verificadas. Las exclusiones no detectan exhaustivamente urgencias ni validan autenticidad.

| Flujo | Consulta | Acciones |
|---|---|---|
| Notificación de éxito | `from:ci@example.com subject:"build succeeded"` | Omitir Recibidos + `99_ARCHIVE`; marcar leído solo si no exige acción |
| Facturas/recibos rutinarios | `from:billing@example.com {subject:invoice subject:factura subject:receipt} -subject:overdue -subject:pendiente -subject:failed -subject:rejected` | Omitir Recibidos + `03_RECORDS`; **no** marcar leído |
| Boletín deseado | `from:newsletter@example.com` | Omitir Recibidos + `04_KNOWLEDGE`; conservar no leído |
| Alias de lectura | `to:usuario+lectura@example.com` | Omitir Recibidos + `04_KNOWLEDGE` |
| Alias documental | `to:usuario+facturas@example.com -subject:overdue -subject:pendiente -subject:failed` | Omitir Recibidos + `03_RECORDS`; conservar no leído |

- No archives indiscriminadamente `category:updates`: puede contener alertas importantes.
- Revisa documentos no leídos a diario. Si exigen pago/respuesta, añade `01_ACTION` y devuelve a Inbox. Para proveedores con urgencias mezcladas, comienza etiquetando **sin** omitir Inbox.
- No uses «Nunca enviar a Spam» en reglas amplias. `from:` no prueba autenticidad.
- Los filtros de Gmail pueden coincidir simultáneamente: un filtro VIP no neutraliza necesariamente otro que archive. Excluye al VIP en **cada** regla de archivado. La prioridad de primera coincidencia solo corresponde al CLI.
- Un filtro de entrada con `older_than:` no se ejecuta meses después para limpiar mensajes que hayan envejecido.

**Alias `+tag`:** utiliza `+lectura`, `+facturas` y `+servicios` en nuevas altas. Todos llegan a la misma cuenta; `example.com` solo ilustra el formato. Usa tu dirección real y prueba recepción/filtro antes de cambiar un servicio importante. Algunos formularios no aceptan `+`. No es identidad separada, permiso ni barrera antispam; la dirección base es deducible. [Variaciones de dirección](https://support.google.com/a/users/answer/9282734?hl=en).

### 2. Cinco etiquetas principales; jerarquía opcional

| Principal | Finalidad | Color / visibilidad | Subetiqueta opcional |
|---|---|---|---|
| `01_ACTION` | Tengo que actuar | Rojo; siempre visible | Ninguna |
| `02_WAITING` | Espero respuesta | Naranja; siempre visible | Ninguna |
| `03_RECORDS` | Documentación conservada | Verde; mostrar si hay no leídos | `03_RECORDS/Facturas` |
| `04_KNOWLEDGE` | Lectura elegida | Azul; mostrar si hay no leídos | `04_KNOWLEDGE/Boletines` |
| `99_ARCHIVE` | Referencia operativa | Gris; oculta | `99_ARCHIVE/Notificaciones` |

Asigna color y visibilidad desde el menú de cada etiqueta; crea las subetiquetas bajo su principal. Los prefijos permiten distinguir estados sin depender del color. Son cinco etiquetas principales, no cinco por servicio.

No crees hijos hasta que aporten una búsqueda útil. Añade los nombres completos de `03_RECORDS/Facturas` y `04_KNOWLEDGE/Boletines` a `settings.protected_labels` si los utilizas: **proteger el padre no protege automáticamente el hijo**. `99_ARCHIVE` no es la acción Archivar; se puede quitar Inbox sin añadir esa etiqueta.

### 3. Rutina diaria, atajos y desuscripción

**Dos ventanas diarias de 10-15 minutos; revisión semanal de 20 minutos.**

1. Inbox: resolver lo breve; lo pendiente va a `01_ACTION`; lo resuelto se archiva.
2. Al delegar: usar `02_WAITING`, fijar fecha en calendario/tareas y archivar.
3. Revisar documentos no leídos; convertir vencimientos reales en acciones.
4. Consumir `04_KNOWLEDGE` en un horario separado; cancelar lo que ya no eliges leer.
5. Semanalmente: revisar esperas, filtros, ruido y muestras del archivo.

```text
label:01_ACTION
label:02_WAITING older_than:7d
label:03_RECORDS is:unread
label:04_KNOWLEDGE is:unread
in:inbox older_than:7d
```

La edad del correo no es una fecha de vencimiento/delegación. Gmail guarda el mensaje; calendario o tareas guardan el compromiso.

Activa atajos en Configuración → General → Combinaciones de teclas:

| Tecla | Acción |
|---|---|
| `/` | Buscar |
| `j` / `k` | Navegar |
| `x` | Seleccionar |
| `e` | Archivar |
| `l` | Aplicar etiqueta |
| `r` | Responder |
| `g` y después `i` | Ir a Inbox |
| `z` | Deshacer la última acción disponible; no es backup |
| `?` | Mostrar ayuda |

Dependen de teclado, idioma y contexto; no los uses dentro de un borrador esperando actuar sobre Inbox. [Atajos oficiales](https://support.google.com/mail/answer/6594?co=GENIE.Platform%3DDesktop&hl=en).

**Plantillas revisadas antes de enviar.** Habilita Plantillas en Configuración → Avanzadas. Redacta el texto y usa Más opciones → Plantillas → Guardar borrador como plantilla. Revisa destinatarios, fechas y adjuntos al reutilizar. [Configuración oficial](https://support.google.com/mail/answer/14864208?hl=en).

```text
RECIBIDO
Recibí [documento/solicitud]. Revisaré [alcance] y responderé antes de [fecha].

FALTA INFORMACIÓN
Para avanzar con [asunto], necesito [dato 1] y [dato 2]. ¿Puedes enviarlos antes de [fecha]?

SEGUIMIENTO
Retomo [asunto]. Quedó pendiente [entregable]. ¿Puedes confirmar el estado y la fecha prevista?
```

**Protocolo de desuscripción:**

- Cancelar solo listas legítimas reconocidas, desde Gmail o el sitio oficial. No abrir enlaces de baja sospechosos: denunciar spam/phishing.
- Si aparece «Administrar suscripciones», revisar remitente y alcance; una baja puede afectar más de un tipo de envío. [Alcance de la baja](https://support.google.com/mail/answer/15621070).
- No cancelar seguridad, facturación ni recuperación de cuenta para reducir ruido; ajustar preferencias en el servicio oficial.
- Registrar la baja localmente y comprobar después que cesaron envíos. No asumir efecto inmediato ni borrado del historial. [Desuscripción en Gmail](https://support.google.com/mail/answer/15433283).
- Auditar semanalmente las cinco listas más ruidosas. No crear borrado automático para compensar altas ilimitadas.

Ninguna rutina se programa ni ejecuta por descargar el repositorio.
