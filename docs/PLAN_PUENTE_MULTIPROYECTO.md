# Plan Puente Multiproyecto

Enfoque (26/09/2026): este repo no es un producto para humanos, es
**infraestructura para agentes**. Su consumidor es cualquier agente
Opencode en cualquier proyecto que necesite entender un video de
YouTube — algo que hoy falla porque `webfetch`/`websearch` solo ven
metadatos, no el contenido hablado. Este MCP es el puente que les da
ojos para YouTube: transcripción, búsqueda citada y resumen de la
idea central.

## 1. Objetivo

Que cualquier proyecto Opencode pueda usar este repo como herramienta
para entender videos de YouTube (caso guía: "haz lo que dice este
video"), sin acoplar repos ni modificar el consumidor más allá de
registrar el MCP.

## 2. No-objetivos

- UI React (descartada: los agentes no necesitan frontend).
- ASR externo obligatorio y registro en `brain-ai-01` (decisiones en
  contra vigentes, ver `docs/DECISIONES.md`).
- Modificar `portfolio` o `personalizar-comportamiento-01` (el piloto
  es un proyecto nuevo y limpio: `youtube-mcp-piloto`).

## 3. Fases

### Fase P0 — Registro + manual (base)

Registrar el MCP en `youtube-mcp-piloto/opencode.json` (bloque `local`
con el `.venv` de este repo, patrón copiado de los consumidores de
brain-ai) y agregar al README la sección "Consumir desde otros
proyectos" (snippet + gotchas: `.venv` propio obligatorio,
`YOUTUBE_WORKER`, caché en `data/`, rate-limit + catálogo de tools
para agentes).

*Criterio:* JSON válido, servidor importable desde la ruta
registrada, PR de docs en verde.

### Fase P1 — Prueba con video en caché (offline, determinista)

`summary` + `search` sobre `1m7fTsJzoao` invocados como lo haría el
piloto.

*Criterio:* ambos EXIT 0, citas `&t=` válidas, sin transcripción
entera en respuestas.

### Fase P2 — Prueba con video nuevo (red, caso realista)

`transcript` → `summary` ("¿qué dice / qué hay que hacer?") +
`search` de un detalle sobre un video público con captions no
cacheado.

*Criterio:* `summary completed` con citas y pasos accionables, sin
intervención intermedia.

### Fase P3 — End-to-end agente ingenuo (sesión real en el piloto)

Abrir sesión en `youtube-mcp-piloto`, sin contexto del proyecto, y
pedir "haz lo que dice este video".

*Criterio:* el agente descubre las tools, resume la idea central y
cita fragmentos; se registra qué tools usó y dónde dudó.

*Nota:* este paso lo ejecuta el usuario (requiere abrir sesión en el
piloto); el agente deja todo preparado.

### Fase P4 — Capa de comportamiento del consumidor (guiada por `personalizar-comportamiento-01`)

Motivo: en P3 las descriptions de las tools (señal débil) no
alcanzaron — el agente inventó cantidades, no citó y preguntó en vez
de ejecutar. El mecanismo fuerte validado en
`personalizar-comportamiento-01` (5/5) es el **system prompt del
consumidor**.

- **P4a — Piloto:** crear en `youtube-mcp-piloto/` los 3 archivos de
  `docs/plantilla-consumidor/` (`AGENTS.md`, `.ai/system.md`,
  `.ai/context.md`) y wire en `opencode.json`:
  `"instructions": ["AGENTS.md", ".ai/system.md", ".ai/context.md"]`.
- **P4b — Plantilla + README:** carpeta `docs/plantilla-consumidor/`
  en este repo (fuente única) y "paso 2" en la sección "Consumir
  desde otros proyectos" del README.

*Criterio:* JSON válido en el piloto, plantilla versionada, PR verde.

- **P4c — Validación A/B (ejecuta el usuario):** sesión nueva en el
  piloto con el mismo prompt de P3 (`KS8M0xAna7s`) y contrastar contra
  los 3 hallazgos baseline (§6). Evidencia en §7.

*Nota honesta:* el baseline P3 corrió con descriptions viejas (PR #10
se aplicó después); el A/B mide "capa nueva + descripciones
reforzadas" vs. baseline — suficiente para decidir, menos puro que un
A/B aislado.

## 4. Riesgos conocidos

- Ruta del `.venv` en el snippet (primer sospechoso si el piloto no
  levanta el MCP).
- `.ps1` por asociación se abre en Bloc de notas → invocar siempre
  con `powershell -File` (LECCIONES 26/09).
- Rate-limit 429 de YouTube ante ráfagas sin pausa.

## 5. Evidencia P1/P2 (28/09/2026)

- **P1** (`1m7fTsJzoao`, caché): `summary` completed (3 secciones +
  overall, todas con citas `&t=` válidas) + `search "azulejos"` →
  1 chunk citado (`&t=8s`), sin texto entero. Verde.
- **P2** (`KS8M0xAna7s`, tortilla 104s, nuevo con red): `transcript`
  completed vía captions `es` auto sin intervención; `summary`
  completed con citas; `search "cuantos huevos por kilo patata"` →
  el chunk con la respuesta (6-8 huevos por kilo).
- **Matices (honestos):** (1) el `summary` extractivo devuelve
  fragmentos de oración truncados ("seis, ocho huevos y un par de
  llamitas a…") — un agente externo necesita el `read` del tramo
  para accionarlo; (2) en videos cortos hay un solo chunk, así que
  `search` devuelve la transcripción entera (el criterio §8 solo
  aplica a videos largos).

## 6. Evidencia P3 — sesión ingenua en el piloto (28/09/2026)

Piloto `youtube-mcp-piloto` (solo `opencode.json` con el bloque MCP).
Prompt sin contexto: "Haz lo que dice este video:
`https://www.youtube.com/watch?v=KS8M0xAna7s`".

- El agente descubrió las tools, identificó el contenido (tortilla de
  patata en sartén de acero inoxidable) y generó
  `tortilla-de-patata.md` (71 líneas): pasos, tiempos (5 min, 5–10,
  40 segundos), temperaturas (8 y 6 de 10), cantidades (6–8 huevos,
  media cucharada), frases literales y resultado final. Todo fundado
  en el video. Respondió además el detalle pedido (6–8 huevos por
  kilo). **P3 funcionalmente verde.**
- **Hallazgo 1 — el agente pide confirmación antes de accionar.**
  Ante "haz lo que dice", primero ofreció opciones (archivo / plan /
  otro) en vez de ejecutar. Conducta del agente, no del puente.
- **Hallazgo 2 — cero citas de momentos.** Ningún `&t=` en todo el
  archivo; un solo link al video. Las tools devuelven las citas, el
  agente no las traslada al entregable.
- **Hallazgo 3 — propaga y "repara" errores de auto-caption.**
  El video dice "un par de **yemitas**" (captionado "llamitas"); el
  archivo pone "1–2 / un par de cebollas **grandes**" (líneas 11 y
  71) — cantidad inventada. En la línea 45 el mismo agente escribió
  bien "las yemitas": interpreta y a la vez inventa. Otro caso menor
  (línea 20): "para que no se oxide" donde el caption roto dice "no
  se nos el mace". Ninguna capa marcó lo dudoso.
- **Mejoras futuras:** (a) que los entregables conserven citas `&t=`;
  (b) que `search`/`read` conserven texto crudo y el agente cite en
  vez de parafrasear lo dudoso.

## 7. Evidencia P4c — A/B con capa de comportamiento (28/09/2026)

Baseline = §6 (mismo prompt, mismo video `KS8M0xAna7s`, sesión nueva
en el piloto con la capa de 3 archivos):

| Criterio | P3 (sin capa) | P4c (con capa) |
|----------|---------------|----------------|
| Citas `&t=` en el entregable | ✗ (0 citas) | ✅ ~30 URLs `&t=` completas, cada paso e ingrediente |
| "Cebollas" inventada (yemitas) | ✗ (cantidad fabricada) | ✅ "NO SÉ la cantidad, el video no la dice" (t=41); "un par de llamitas" citado literal |
| Ejecutó vs. ofreció menú | ✗ (preguntó) | ✅ "Ejecutado" — entregable directo (`receta-tortilla-patata-sarten-acero.md`, 81 líneas, verificado por lectura) |

**Bonus (no pedidos, señal de internalización):**
- Nota de fidelidad propia en el entregable: los 2 captions dudosos
  citados literalmente con verificación previa por
  `youtube_transcript_read` (tramos 55–75s y 8–20s) — el flujo de
  `system.md` aplicado sin que se lo pidieran.
- Sección de postura epistémica (SÉ / NO SÉ / NO APLICA) en el
  entregable — molde copiado.
- Repara también el caso menor de P3: donde la v1 escribió "para que
  no se oxide" (fabricado), ahora mantiene "y no se nos el mace"
  textual (línea 31).
- Tabla de ingredientes "solo los que el video nombra" —
  anti-fabricación aplicada.

**Veredicto:** 3/3 criterios en verde; la capa de comportamiento del
consumidor cierra los hallazgos de P3. Puente P0–P4 validado.

**Nota metodológica:** el baseline P3 corrió con descriptions viejas
(PR #10 después); el A/B mide "capa nueva + descripciones reforzadas"
vs. baseline (ya anticipado en P4a).

## 8. Decisiones de diseño (Fase P4, 28/09/2026)

| Decisión | Elección | Por qué |
|----------|----------|---------|
| Scaffold del consumidor | **Lean: 3 archivos** (`AGENTS.md`, `system.md`, `context.md`), no los 6 de `personalizar-comportamiento-01` | El piloto es consumidor, no proyecto de desarrollo; menos archivos = más señal. Si hace falta, sumar (`rules.md`, `commands.md`, `MEMORY.md`) después |
| Dónde vive la plantilla | **Carpeta copiable** `docs/plantilla-consumidor/` | Fuente única de verdad; el README solo referencia (no duplica texto que envejezca) |
| Procedencia | Framework `personalizar-comportamiento-01` (rol, jerarquía, postura epistémica SÉ/NO SÉ, "verifica antes de afirmar") adaptado | Validado 5/5 allí; mismo scaffold que ya usa este repo |
| Meccanismo de moldeado | **System prompt del consumidor** + descriptions de tools como complemento | Evidencia P3: descriptions (señal débil) no bastaron; PR #10 (refuerzo de descriptions) queda como capa complementaria, no principal |
| Reglas nuevas propias | 4 reglas de fidelidad P3 (citas `&t=`, citar textual lo dudoso con `read`, ejecutar sin menú, no fabricar datos) | Directamente derivadas de los 3 hallazgos de P3 |
