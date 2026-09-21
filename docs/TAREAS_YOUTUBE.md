# Tareas - Análisis de Videos YouTube (servidor MCP propio)
Ultima actualizacion: 21/09/2026

---

## 1. Objetivo

Permitir que el asistente analice el contenido hablado de videos públicos de
YouTube a partir de su URL: extraer la transcripción (con timestamps),
cachearla, buscar fragmentos relevantes y responder con citas temporales,
al estilo NotebookLM pero 100% gratis y sin APIs de pago.

El módulo se expone vía tools MCP en un **servidor MCP propio** de este
repositorio (youtube-transcripts), independiente de brain-ai-01.

Alcance v1: videos públicos, español e inglés, sin autenticación,
sin playlists, sin directos, duración máxima 2h. Sin análisis visual
(solo audio/habla). Sin componente UI en el portfolio (es estático);
la integración visual se definirá después del v1.

---

## 2. Cómo llegamos a esta solución

1. Pregunta inicial: "si te paso un link de youtube puedes analizar el contenido?"
2. Verificación propia: `webfetch`/`websearch` solo sirven para metadatos;
   no procesan audio/video.
3. Investigación web: NotebookLM no transcribe audio, solo importa captions
   existentes de YouTube. Su valor real es el RAG sobre la transcripción.
4. Investigación externa (4 docs en `docs/investigacion-youtube/`):
   - `youtube tras-gpt-5.6-01.md` — pipeline escalonado + correcciones
     (u-transkript no es fallback real; API oficial no sirve; faster-whisper
     local no necesita key) + arquitectura + riesgos + plan en 4 fases.
   - `youtube tras-gpt-5.6-02.md` — solución 100% gratis + código base
     `YouTubeService` + jobs SQLite + chunking/FTS5 + visual opcional.
   - `youtube-trans-clau-45-01.md` — comparativa 5 opciones + código
     `yt_analyze` + hook/componente React + tests pytest.
   - `youtube-trans-clau-45-02.md` — solución 100% gratis + `youtube_analyzer.py`
     completo con NLP local (spacy/nltk) + FastAPI + MCP.
5. Síntesis propia: convergencia en pipeline captions → yt-dlp → faster-whisper,
   SQLite, 4 tools MCP, por fases. Fuera del v1: contenido visual y UI React.
6. Decisión de desacople MCP: este proyecto expone su propio servidor MCP
   en lugar de registrarse en brain-ai-01, porque no todos los consumidores
   necesitan ambos proyectos a la vez.

---

## 3. Decisión de arquitectura

### 3.1 Servidor MCP propio (independiente de brain-ai-01)

- Este repositorio incluye `mcp_server.py` que expone la tool
  `youtube_transcript` (y en fases siguientes `status`, `read`, `search`).
- **No se modifica** `brain-ai-01/mcp_bridge.py` en la Fase 1.
- Justificación: los consumidores son distintos — unos usan
  youtube-transcripts, otros brain-ai-01; no todos necesitan ambos.
  Acoplarlos obligaría a cargar dependencias no usadas.
- El servidor se registra en `opencode.json` como MCP local.

### 3.2 Pipeline escalonado (el primero que tenga éxito gana)

1. `youtube-transcript-api` — captions existentes (rápido, ~2s).
2. `yt-dlp` — subtítulos manuales/automáticos sin descargar video.
3. `yt-dlp` (solo audio) + `faster-whisper` local (modelo `small`,
   CPU int8) — fallback real sin captions.
4. ASR externo (OpenAI/Deepgram) — solo como adaptador opcional, no obligatorio.

Infraestructura: SQLite (caché + jobs + FTS5), worker separado para ASR,
sin Redis/PostgreSQL/servicios pagos. Solo videos públicos en v1.

Orden de preferencia de pistas:
manuales idioma pedido → manuales original → automáticas pedido →
automáticas original → traducción → ASR. Siempre guardar idioma, fuente,
manual/auto, motor y fecha.

---

## 4. Pros y contras

### Pros
- 100% gratis, sin API keys obligatorias, todo local/offline tras descargas.
- Funciona en Windows, integra directo con Python/MCP.
- Cubre ~85% de videos en segundos (captions) y el resto con ASR local.
- SQLite: sin infraestructura adicional.
- Diseño por fases: valor desde Fase 1.
- Servidor MCP propio: repo autocontenido, sin acoplar brain-ai-01.

### Contras / riesgos
- YouTube puede bloquear IP / HTTP 429 (más en cloud que en residencial).
- `youtube-transcript-api` y `yt-dlp` usan endpoints no oficiales:
  mantenimiento continuo, fijar versiones + tests de integración.
- ASR en CPU tarda minutos en videos largos (jobs async obligatorios).
- Sin captions + ASR: timestamps menos precisos, errores en nombres propios.
- ToS/copyright: solo a petición, borrar audio, no redistribuir.
- No cubre contenido puramente visual (diapositivas sin narración) en v1.
- Un proceso MCP más que mantener (frente al server central único).

### Descartado y por qué
- API oficial `captions.download`: requiere OAuth y permisos sobre el video.
- `u-transkript` como fallback: sigue necesitando pista de subtítulos.
- `notebooklm-client` / cookies Google: frágil, sesiones que expiran,
  riesgo de bloqueo, no apto para producción.
- `YouTubeTranscript.dev` como base: coste recurrente (dejar como opción).
- OpenAI Whisper API como obligatorio: rompe requisito gratis (opcional OK).
- Registrar tools en `brain-ai-01/mcp_bridge.py`: acopla repos y obliga a
  todos los consumidores a cargar ambos proyectos; se descarta para v1.
- `youtube-transcript-api` legacy 0.6.x (`list_transcripts` + `TextFormatter`):
  no devuelve segmentos con timestamps útiles; se usa API moderna v1.x.

---

## 5. Plan de implementación por fases

### FASE 1 — MVP captions (servidor MCP propio)
- [x] Estructura base: `services/`, `tests/`, `data/`, `__init__.py`
- [x] Dependencias: instalar y fijar `youtube-transcript-api==1.2.4`
      (API moderna v1.x `fetch()`, no legacy 0.6.x), `pytest`,
      `pytest-asyncio`, `mcp`
- [x] `.gitignore` (`data/`, `.venv/`, `__pycache__/`, `*.db`)
- [x] `services/youtube_urls.py` — parser seguro de URLs
      (whitelist hosts youtube.com/www/m/youtu.be, soporte
      `/watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`,
      ID `[A-Za-z0-9_-]{11}`, rechazo playlists `?list=` y directos
      `/live/`, sin `shell=True`) — 35 tests en verde
      (`tests/test_youtube_urls.py`), lanza `InvalidYouTubeUrl`
- [x] `services/youtube_errors.py` — errores estructurados:
      `invalid_url` / `no_captions` / `blocked` / `duration_exceeded`
      (distinguir "sin captions" de "bloqueado" explícitamente)
      — hecho antes que el parser para que este lance errores tipados;
      6 tests unitarios en verde (`tests/test_youtube_errors.py`)
- [x] `services/youtube_cache.py` — caché SQLite en `data/youtube.db`
      (clave `video_id + lang + track_type`, TTL 7 días, gitignore
      `data/`) — 9 tests en verde (`tests/test_youtube_cache.py`)
- [x] `services/youtube_service.py` — orquestador
      (dataclasses `TranscriptSegment{start,end,text}` y
      `TranscriptResult`, selección pistas manual > auto y es > en,
      límite duración 2h, mapeo de excepciones de la librería a
      nuestros códigos de error) — 16 tests unitarios con mock
      (`tests/test_youtube_service.py`), sin red
- [ ] `mcp_server.py` — servidor MCP propio, tool `youtube_transcript`
      (sync, timeout corto, args: `url`, `languages`, `include_timestamps`;
      respuesta `completed` con segmentos o `error` con code/suggestion)
- [ ] Registrar servidor MCP en `opencode.json`
- [ ] Tests unitarios sin red: parser (IDs válidos/inválidos, playlists,
      live, hosts), caché (hit/miss/TTL), errores, selección de pistas
      con mock — cobertura ≥80%
- [ ] Tests integración con red: 3 videos ES + 3 EN con captions →
      texto + timestamps; video sin captions → `no_captions`
- [ ] Actualizar `README.md` y `.ai/context.md` (servidor MCP propio,
      ya no "tools MCP en brain-ai-01")
- [ ] Guardar decisión en memoria (`brain_ai_memory_save`)
- [ ] Verificación: `pytest tests/ -v` en verde + criterios Fase 1

### FASE 2 — Fallback real (videos sin captions)
- [ ] Integrar `yt-dlp`: listar/descargar subtítulos (VTT→segmentos)
- [ ] Descarga solo-audio (`bestaudio`, template controlado, temp aislado)
- [ ] Instalar FFmpeg (winget/Choco) y `faster-whisper` (`small`, cpu, int8)
- [ ] Tabla `youtube_jobs` en SQLite + worker separado (no solo
      BackgroundTasks: durable, heartbeat, reintentos con backoff)
- [ ] Tools de este servidor: `youtube_transcript_status` + lectura
      paginada (`youtube_transcript_read` con `start/end/max_chars`)
- [ ] Limpieza automática de audio y temporales + política LRU
- [ ] Verificación: video sin captions → `processing` → `completed`,
      texto en español correcto

### FASE 3 — Experiencia tipo NotebookLM (RAG)
- [ ] Chunking 500-1000 tokens, solapamiento 10-15%, sin cortar frases,
      con timestamps
- [ ] Índice SQLite FTS5 (`transcript_chunks_fts`)
- [ ] Tool `youtube_transcript_search` (`transcript_id`, `query`, `top_k`)
- [ ] Respuestas con citas temporales
      (`https://www.youtube.com/watch?v=ID&t=620s`)
- [ ] Resúmenes jerárquicos para videos largos
- [ ] Verificación: preguntar sobre un video largo y recibir fragmentos
      citados, no la transcripción entera

### FASE 4 — Resiliencia y operación
- [ ] Interfaz `TranscriptProvider` (`YouTubeTranscriptApiProvider`,
      `YtDlpSubtitleProvider`, `FasterWhisperProvider`,
      `ExternalAsrProvider` opcional) con enable/disable por config
- [ ] Circuit breaker + backoff con jitter tras 429
- [ ] Métricas por proveedor + endpoint de salud
- [ ] Tests de integración periódicos con videos públicos fijos
- [ ] Cuotas por usuario, concurrencia máxima, retención documentada
- [ ] Documentar decisión en memoria (`brain_ai_memory_save`)

---

## 6. Fuera del alcance del v1

- Análisis visual (frames/OCR/modelo local): futura Fase 5.
- Componente UI React en el portfolio: se definirá después del v1.
- Proveedor ASR externo como dependencia obligatoria: solo adaptador opcional.
- Integración/registro de tools en brain-ai-01: fuera del v1; este proyecto
  expone su propio servidor MCP.

---

## 7. Dependencias

```
youtube-transcript-api==1.2.4   # API moderna v1.x (fetch)
mcp                              # servidor MCP propio
yt-dlp                           # Fase 2
faster-whisper                   # Fase 2
FFmpeg (sistema, winget/Choco)   # Fase 2
SQLite (stdlib) + FTS5           # Fase 3
pytest, pytest-asyncio           # tests
```

Fijar versiones en `requirements.txt` tras validar con el Python local
(3.10.7). No fijar precios de proveedores en código (tratar como config).

> **Instalar siempre en `.venv` local** (`.venv\Scripts\pip install -r requirements.txt`),
> nunca en el Python global. Motivo: `mcp` arrastra `starlette>=0.49` y
> rompe `fastapi` de brain-ai-01 (requiere `starlette<0.38`); ambos
> comparten el mismo intérprete 3.10.7. Verificado 21/09/2026.

---

## 8. Criterios de aceptación v1 (Fases 1-4)

- [ ] Video ES con captions → transcripción en <10s vía servidor MCP propio
- [ ] Video EN con captions → transcripción con idioma detectado
- [ ] Video sin captions → job async → transcripción local correcta
- [ ] Video largo → `search` devuelve chunks citados con `&t=`
- [ ] Repetir mismo video usa caché (sin re-extracción)
- [ ] URL inválida / video privado / playlist → error claro, sin crash
- [ ] Audio temporal siempre eliminado tras ASR
- [ ] brain-ai-01 no modificado en Fase 1

---

## 9. Estructura de archivos objetivo

```
youtube-transcripts/
├── services/
│   ├── __init__.py
│   ├── youtube_urls.py        # parser seguro de URLs
│   ├── youtube_cache.py       # caché SQLite
│   ├── youtube_errors.py      # errores estructurados
│   └── youtube_service.py     # orquestador + captions
├── mcp_server.py              # servidor MCP propio (youtube_transcript)
├── tests/
│   ├── __init__.py
│   ├── test_youtube_urls.py
│   ├── test_youtube_cache.py
│   ├── test_youtube_service.py
│   └── test_mcp_server.py
├── data/                      # youtube.db (gitignored)
├── requirements.txt
├── opencode.json              # registro del servidor MCP
├── README.md
└── docs/
    ├── TAREAS_YOUTUBE.md
    └── investigacion-youtube/
```

---

## 10. Referencias

- `investigacion-youtube/youtube tras-gpt-5.6-01.md`
- `investigacion-youtube/youtube tras-gpt-5.6-02.md`
- `investigacion-youtube/youtube-trans-clau-45-01.md`
- `investigacion-youtube/youtube-trans-clau-45-02.md`
- https://github.com/jdepoix/youtube-transcript-api
- https://github.com/yt-dlp/yt-dlp
- https://github.com/SYSTRAN/faster-whisper
- https://developers.google.com/youtube/v3/docs/captions/download
