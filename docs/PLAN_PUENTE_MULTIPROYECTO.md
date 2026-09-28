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
