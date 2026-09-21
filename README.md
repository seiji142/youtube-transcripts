# youtube-transcripts

Análisis de contenido hablado de videos públicos de YouTube, al estilo
NotebookLM pero 100% gratis y sin APIs de pago. Módulo Python con
servidor MCP propio que expone transcripción con timestamps.

## Estado

Planificación (Fases 1-4). Ver `docs/TAREAS_YOUTUBE.md`.

## Estructura

| Ruta | Contenido |
|------|-----------|
| `docs/TAREAS_YOUTUBE.md` | Plan, fases, criterios de aceptación |
| `docs/investigacion-youtube/` | 4 docs de investigación externa |
| `services/` | Código del pipeline (vacío hasta Fase 1) |
| `mcp_server.py` | Servidor MCP propio (desde Fase 1) |
| `tests/` | Tests pytest (desde Fase 1) |
| `requirements.txt` | Dependencias (versiones se fijan en Fase 1) |
| `.ai/` | Contexto del proyecto para el agente |

## Pipeline (resumen)

```
youtube-transcript-api (captions)
  → yt-dlp subtítulos
    → yt-dlp audio + faster-whisper local
      → SQLite caché + jobs + FTS5
        → tools MCP: transcript / status / read / search
```

## Integración

Servidor MCP **propio** (`mcp_server.py`), independiente de `brain-ai-01`.
No todos los consumidores necesitan ambos proyectos; este repo es
autocontenido (lógica + exposición MCP). Registro en `opencode.json`.
