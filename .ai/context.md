# Contexto del Proyecto

## Stack Tecnologico

- **Lenguaje:** Python 3.10+
- **Servidor MCP:** propio (`mcp_server.py` en este repo), independiente
  de brain-ai-01 (no todos los consumidores necesitan ambos)
- **Extracción:** youtube-transcript-api → yt-dlp → faster-whisper (ver plan)
- **Base de datos:** SQLite (caché + jobs + FTS5, sin servidor externo)
- **Sistema:** Windows (winget/Choco para FFmpeg)

## Dependencias Principales

Versiones se fijan en Fase 1 (ver `docs/TAREAS_YOUTUBE.md` seccion 7):

- `youtube-transcript-api==1.2.4` (captions, primera ruta, API v1.x)
- `yt-dlp==2026.8.19` (subtítulos fallback, Fase 2 parcial — sin audio aún)
- `mcp` (servidor MCP propio)
- `faster-whisper` (ASR local, modelo `small`, CPU int8) — Fase 2 pendiente
- `pytest`, `pytest-asyncio` (tests)

## Variables de Entorno

Ninguna obligatoria en v1. `OPENAI_API_KEY` solo si se habilita el adaptador
ASR externo opcional (Fase 4). Nunca commitear `.env`.

## Arquitectura

Pipeline escalonado: el primer proveedor que tenga éxito gana.
Orden: captions → subtítulos yt-dlp → audio + faster-whisper → (opcional) ASR externo.
Resultados con `{start, end, text}` + metadatos (idioma, fuente, motor, fecha).

### Tools MCP (servidor propio, implementadas por fases)

| Tool | Fase | Funcion |
|------|------|---------|
| `youtube_transcript` | 1 | Extrae transcripción (sync, captions) |
| `youtube_transcript_status` | 2 | Estado de job ASR async |
| `youtube_transcript_read` | 2 | Lectura paginada por rango |
| `youtube_transcript_search` | 3 | Búsqueda FTS5 con citas `&t=` |

## Convenciones de Archivos

| Tipo | Destino | Ejemplo |
|------|---------|---------|
| Servicios/pipeline | `services/` | `youtube_service.py` |
| Fallback subtítulos | `services/youtube_subtitles.py` | parser VTT + yt-dlp |
| Servidor MCP | raíz | `mcp_server.py` |
| Tests | `tests/` | `test_youtube_service.py` |
| Docs de plan | `docs/` | `TAREAS_YOUTUBE.md` |
| Investigación | `docs/investigacion-youtube/` | `youtube tras-gpt-5.6-01.md` |
| Dependencias | raíz | `requirements.txt` |

## Comandos Disponibles

| Comando | Descripcion |
|---------|-------------|
| `pip install -r requirements.txt` | Instalar dependencias |
| `pytest tests/ -v` | Ejecutar tests (vía `run_tests`) |
| `winget install Gyan.FFmpeg` | Instalar FFmpeg en Windows |
