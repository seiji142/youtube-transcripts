# Contexto del Proyecto Consumidor

## Stack Tecnológico

- Cliente MCP de **youtube-transcripts** (registrado en `opencode.json`).
- Videos públicos de YouTube, español e inglés, duración ≤2h.

## Tools MCP disponibles

| Tool | Para qué |
|------|----------|
| `youtube_transcript` | Extraer transcripción (devuelve `processing` + `job_id` si no hay captions) |
| `youtube_transcript_status` | Estado de un job ASR (`job_id` o URL) |
| `youtube_transcript_read` | Leer tramo por segundos (`start`/`end`/`max_chars`) — verificación de tramos dudosos |
| `youtube_transcript_search` | Búsqueda BM25 con citas `&t=` (requiere transcripción previa) |
| `youtube_transcript_summary` | Idea central: secciones + overall con citas `&t=` |
| `youtube_health` | Diagnóstico: proveedores, breakers, métricas |

## Gotchas

- La **caché** vive en el repo `youtube-transcripts` (`data/`,
  SQLite): videos ya consultados responden offline.
- `status=processing` → llamar `youtube_transcript_status` con
  `job_id`; no reintentar `youtube_transcript` a ciegas.
- **Rate-limit de YouTube (429):** no sondear en ráfaga; respetar
  pausas ante errores de bloqueo.
- Videos >2h, playlists y directos son rechazados por diseño.

## Convenciones de Archivos

| Tipo | Destino |
|------|---------|
| Entregables derivados de videos (recetas, planes, resúmenes) | raíz o `docs/` del proyecto consumidor |

## Reglas de Comportamiento

Ver `.ai/system.md` (postura epistémica + reglas de fidelidad al
video). Este scaffold se adaptó de `personalizar-comportamiento-01`
(versión lean: 3 archivos).
