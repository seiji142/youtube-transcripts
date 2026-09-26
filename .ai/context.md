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
- `yt-dlp==2026.8.19` (subtítulos fallback + descarga solo-audio, Fase 2)
- FFmpeg 9.0.2 (sistema, winget `Gyan.FFmpeg`) — convierte audio→wav
- `faster-whisper==1.2.1` (ASR local, modelo `small`, CPU int8) — Fase 2
- `mcp` (servidor MCP propio)
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
| `youtube_transcript` | 1 | Extrae transcripción (sync: captions → subtítulos; sin captions encola job ASR → `processing`) |
| `youtube_transcript_status` | 2 | Estado de job ASR async (`job_id` o URL) |
| `youtube_transcript_read` | 2 | Lectura paginada por rango en segundos (`start/end/max_chars`) |
| `youtube_transcript_search` | 3 | Búsqueda FTS5 con citas `&t=` |

### Archivos de servicio (Fase 2)

| Archivo | Rol |
|---------|-----|
| `services/youtube_service.py` | orquestador (captions + fallback subtítulos) |
| `services/youtube_subtitles.py` | fallback yt-dlp (parser VTT) |
| `services/youtube_audio.py` | descarga solo-audio → wav (FFmpeg) |
| `services/youtube_asr.py` | ASR local faster-whisper (small/cpu/int8) |
| `services/youtube_jobs.py` | jobs ASR durables (SQLite, backoff, heartbeat) |
| `services/youtube_worker.py` | worker ASR (thread daemon) + sweep de temporales |

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

## Ramas del Proyecto

> Setup gitflow 23/09/2026 (fuente: repo `seiji142/gitflow-scaffold`,
> versión `2026.09.25` aplicada 25/09; decisiones en
> `docs/DECISIONES.md`, checklist en `docs/gitflow-scaffold.md`).

| Rama | Proposito | Sale de | Vuelve a | Proteccion |
|------|-----------|---------|----------|------------|
| `main` | Produccion (GitHub default) | — | — | Requiere PR, SIN "Require approvals" |
| `develop` | Desarrollo diario (rama por defecto) | `main` | `main` (PR al publicar) | No |
| `feature/<desc>` | Cada tarea o experimento | `develop` | `develop` (PR) | No |

Reglas de comportamiento:
- Trabajar SIEMPRE en `develop`. Antes de modificar, verificar la rama con
  `git_ver_estado`/`git branch`; si se está en `main`, no trabajar ahí.
- `main` solo se toca para publicar, vía PR desde `develop`.
- Tareas grandes: `feature/<desc>` desde `develop`, merge de vuelta a `develop`.
- Protección de `main`: "Require a pull request" SIN "Require approvals"
  (repo personal: el autor no puede aprobar su propio PR → bloqueo permanente).
- GitHub Pages/`deploy.yml` **NO aplica** a este repo (Python/MCP, sin build
  estático) — decisión Q1 de `docs/DECISIONES.md`.
