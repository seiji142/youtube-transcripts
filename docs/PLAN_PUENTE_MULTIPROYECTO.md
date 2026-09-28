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
