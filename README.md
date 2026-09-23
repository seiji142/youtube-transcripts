# youtube-transcripts

Análisis de contenido hablado de videos públicos de YouTube, al estilo
NotebookLM pero 100% gratis y sin APIs de pago. Módulo Python con
servidor MCP propio que expone transcripción con timestamps.

## Estado

**Fase 1 y Fase 2 completas**: captions + subtítulos yt-dlp, audio
+FFmpeg, ASR local faster-whisper (verificado real: `es` prob 1.00),
jobs async con worker durable, tools `status`/`read`.
Suite offline **186/186**; integración con red **8/8** (22/09);
verificación ASR real **PASS** (23/09, ver `docs/LECCIONES.md`).

Siguiente: **Fase 3** (RAG/FTS5 + tool `search`). Ver
`docs/TAREAS_YOUTUBE.md`.

## Estructura

| Ruta | Contenido |
|------|-----------|
| `services/` | Pipeline: `youtube_urls`, `youtube_errors`, `youtube_cache`, `youtube_service`, `youtube_rate_limit`, `youtube_subtitles`, `youtube_audio`, `youtube_asr`, `youtube_jobs`, `youtube_worker` |
| `mcp_server.py` | Servidor MCP propio (`youtube_transcript`, `_status`, `_read`) + thread worker ASR |
| `tests/` | 186 unit + 8 integración (marcador `integration`) |
| `data/` | SQLite local (caché + jobs, gitignored) |
| `docs/TAREAS_YOUTUBE.md` | Plan, fases, decisiones, criterios de aceptación |
| `docs/investigacion-youtube/` | 4 docs de investigación externa |
| `requirements.txt` | Deps fijadas (instalar en `.venv`, no global) |
| `.ai/` | Contexto del proyecto para el agente |
| `opencode.json` | Config + registro del servidor MCP |

## Pipeline (resumen)

```
youtube-transcript-api (captions)   ← Fase 1 ✅
  → yt-dlp subtítulos                ← Fase 2 ✅ (fallback implementado)
    → yt-dlp audio + faster-whisper  ← Fase 2 ✅ (worker async, verificado real)
      → SQLite caché ✅ + jobs ✅ + FTS5 (Fase 3)
        → tools MCP: transcript ✅ / status ✅ / read ✅ / search (Fase 3)
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

# FFmpeg (requerido para audio→wav; solo 1ª vez)
winget install Gyan.FFmpeg

# Tests unitarios (default, sin red)
.venv\Scripts\python -m pytest tests/ -m "not integration"

# Tests integración (con red, requiere YouTube accesible)
.venv\Scripts\python -m pytest tests/test_integration.py -m integration

# Arrancar servidor MCP (stdio) — incluye worker ASR (thread daemon;
# desactivar con YOUTUBE_WORKER=0)
.venv\Scripts\python mcp_server.py
```
