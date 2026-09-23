# youtube-transcripts

Análisis de contenido hablado de videos públicos de YouTube, al estilo
NotebookLM pero 100% gratis y sin APIs de pago. Módulo Python con
servidor MCP propio que expone transcripción con timestamps.

## Estado

**Fase 1 completa** (MVP captions + servidor MCP propio) +
**Fase 2 parcial** (fallback subtítulos yt-dlp implementado).
Suite offline **108/108**; integración con red **8/8** (22/09).

Pendiente Fase 2: audio + faster-whisper + jobs async.
Ver `docs/TAREAS_YOUTUBE.md`.

## Estructura

| Ruta | Contenido |
|------|-----------|
| `services/` | Pipeline: `youtube_urls`, `youtube_errors`, `youtube_cache`, `youtube_service`, `youtube_rate_limit`, `youtube_subtitles` |
| `mcp_server.py` | Servidor MCP propio (tool `youtube_transcript`) |
| `tests/` | 108 unit + 8 integración (marcador `integration`) |
| `data/` | SQLite local (caché, gitignored) |
| `docs/TAREAS_YOUTUBE.md` | Plan, fases, criterios de aceptación |
| `docs/investigacion-youtube/` | 4 docs de investigación externa |
| `requirements.txt` | Deps fijadas (instalar en `.venv`, no global) |
| `.ai/` | Contexto del proyecto para el agente |
| `opencode.json` | Config + registro del servidor MCP |

## Pipeline (resumen)

```
youtube-transcript-api (captions)   ← Fase 1 ✅
  → yt-dlp subtítulos                ← Fase 2 ✅ (fallback implementado)
    → yt-dlp audio + faster-whisper  ← Fase 2 (pendiente)
      → SQLite caché ✅ + jobs + FTS5
        → tools MCP: transcript ✅ / status / read / search
```

## Integración

Servidor MCP **propio** (`mcp_server.py`), independiente de `brain-ai-01`.
No todos los consumidores necesitan ambos proyectos; este repo es
autocontenido (lógica + exposición MCP). Registro en `opencode.json`.

## Uso

```bash
# Setup (venv local — NO instalar en Python global)
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Tests unitarios (default, sin red)
.venv\Scripts\python -m pytest tests/ -m "not integration"

# Tests integración (con red, requiere YouTube accesible)
.venv\Scripts\python -m pytest tests/test_integration.py -m integration

# Arrancar servidor MCP (stdio)
.venv\Scripts\python mcp_server.py
```
