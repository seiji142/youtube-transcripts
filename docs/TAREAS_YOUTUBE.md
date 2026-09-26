# Tareas - Análisis de Videos YouTube (servidor MCP propio)
Ultima actualizacion: 23/09/2026

> Historial de decisiones por fase (Fases 1-2, gitflow, 3-4 abiertas):
> **`docs/DECISIONES.md`**. Errores de shell: `docs/LECCIONES.md`.

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

#### Incidente 429 (21/09/2026) — rate limit por volumen

- **Qué pasó:** sondeo de ~25 videos en ráfaga (~50 HTTP requests en
  ~5-8 min, sin pausa entre llamadas) → YouTube devolvió HTTP 429 /
  `IpBlocked`. Los tests de integración no pudieron completarse
  (1 passed / 7 skipped).
- **Diagnóstico:** throttling por volumen desde IP residencial
  (no era bloqueo de cloud/ASN ni IP permanentemente baneada).
- **Umbral:** YouTube **no publica** req/min; cualquier cifra exacta
  es inventada. Consenso comunidad: **≥1s entre requests**.
- **Cobertura actual:** el código detecta/clasifica bien el 429
  (`blocked` estructurado), la caché evita refetch, los tests de
  integración skipan ante bloqueo persistente — pero **no previene**
  la ráfaga en producción.
- **Decisión:** añadir `RateLimiter` preventivo en Fase 1
  (ver §5); circuit breaker + backoff siguen en Fase 4 como
  red de seguridad, no como prevención primaria.
- **Update 21:55:** reintento a los ~55-58 min del primer 429 →
  bloqueo **persiste** (1 video, RateLimiter activo, 1.6s, aún 429).
  Reset estimado en rango de horas. Dejar como tarea de próxima
  sesión; no insistir para no extender el bloqueo.
- **Update 22/09:** bloqueo **levantado**; Nivel 1 OK → suite
  integración **8/8 en verde**. Cierre de la TAREA PENDIENTE (§5).

#### Escenarios de bloqueo — no hay "cuenta" que banear

**Aclaración:** no usamos cuenta de YouTube. `youtube-transcript-api`
**no autentica** (sin login, sin cookies, sin API key). No existe ban
de cuenta en nuestro flujo.

| Tipo de bloqueo | ¿Nos aplica? | Tratamiento |
|-----------------|--------------|-------------|
| Rate limit 429 por volumen | ✅ (incidente 21/09) | Temporal; RateLimiter preventivo ya en Fase 1; esperar reset |
| Ban de IP residencial | Poco probable (requiere uso agresivo sostenido) | Reiniciar router (IP dinámica → nueva IP); esperar 24-48h |
| Ban de IP cloud/ASN | ❌ No (IP residencial, no AWS/GCP) | — |
| Ban de cuenta Google | ❌ No existe (no hay cuenta en el flujo) | — |

**Escalada si el bloqueo persiste (días):**

1. Reiniciar router (gratis, IP dinámica)
2. VPN gratuita (algunas IPs ya baneadas por YouTube; no garantizado)
3. Caché local (videos ya fetcheados no necesitan YouTube)
4. Proxy rotativo (Webshare, integrado en la lib) — **pago, rompe
   "100% gratis"**; dejar como opción documentada, no para v1

**Prohibido (riesgo real):**
- ❌ Autenticar con cookies de cuenta Google: la lib lo permite pero
  **YouTube banea la cuenta** — explícitamente no recomendado
- ❌ Reintentar en loop: empeora el bloqueo
- ❌ Proxies de pago como dependencia de v1

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
- [x] `mcp_server.py` — servidor MCP propio, tool `youtube_transcript`
      (sync, timeout corto, args: `url`, `languages`, `include_timestamps`;
      respuesta `completed` con segmentos o `error` con code/suggestion)
      — MCPServer (mcp 2.x), 6 tests (`tests/test_mcp_server.py`)
- [x] Registrar servidor MCP en `opencode.json` (transporte stdio,
      `.venv` local, independiente de brain-ai-01)
- [x] Tests unitarios sin red: parser (IDs válidos/inválidos, playlists,
      live, hosts), caché (hit/miss/TTL), errores, selección de pistas
      con mock — cobertura ≥80% — **83/83 en verde** (incluye
      RateLimiter y MCP server)
- [x] Tests integración con red: 3 videos ES + 3 EN con captions →
      texto + timestamps; video sin captions → `no_captions`
      — `tests/test_integration.py` creado (8 tests, marcador
      `integration`), videos fijados y verificados; **8/8 en verde
      22/09/2026** tras levantarse el bloqueo 429 (Nivel 1 sonda
      OK → suite completa OK, 34s). Historial: rate limit del
      21/09 tras sondeo de candidatos; reintento 21:55 del mismo
      día aún bloqueado; corte por criterio de no insistir.
- [x] `services/youtube_rate_limit.py` — RateLimiter preventivo
      (propuesto tras incidente 429, ver §4): **1s mínimo entre
      requests** + **máx 10 req / 60s**; integrado en
      `YouTubeService.get_transcript()` solo en cache miss;
      deshabilitable para tests unitarios con mock — 9 tests
      (`tests/test_youtube_rate_limit.py`)
- [x] Tests unitarios del RateLimiter (respeta intervalo, ventana,
      deshabilitado no espera) + 2 tests de integración con
      `YouTubeService` (acquire en miss, no en hit, enabled=False)
- [x] Actualizar `README.md` y `.ai/context.md` (servidor MCP propio,
      ya no "tools MCP en brain-ai-01")
- [x] Guardar decisión en memoria (`brain_ai_memory_save`)
- [x] Verificación offline: `pytest -m "not integration"` en verde
      (**83/83**); brain-ai-01 no modificado; git limpio.
      Integración con red queda como **tarea aparte** (ver checkbox
      `[~]` de tests integración)
      — **Re-verificación 21/09/2026 22:18**: suite offline
      re-ejecutada → **83/83 en verde** (8 integración deselected),
      sin regresiones; reintegración con red sigue pendiente (§5
      TAREA PENDIENTE)

### TAREA PENDIENTE — Próxima sesión
- [x] ~~Reintentar integración~~ **COMPLETADA 22/09/2026**: Nivel 1
      (1 video) OK → suite completa **8/8 en verde**; criterios ES/EN
      (§8) marcados `[x]`

### FASE 2 — Fallback real (videos sin captions)

#### Decisiones — Bloque D (jobs/worker), 23/09/2026

| # | Decisión | Por qué |
|---|----------|---------|
| D1 | **Worker = thread daemon dentro de `mcp_server`** (no proceso aparte) | Un solo proceso que operar en Windows. SQLite (`youtube_jobs`) hace el estado **durable**: si el proceso muere, el job queda `pending`/`processing` y se retoma al reiniciar (`reclaim_stale` por heartbeat vencido). `BackgroundTasks` queda descartado (no durable). Reintentos con backoff vía `attempts`/`next_attempt_at`. |
| D2 | **Integración ASR real → al cierre de Fase 2** (no en este bloque) | El cableado ya está probado (smoke `tiny` PASS 23/09). La corrida con modelo `small` (~460 MB primera vez) + video sin captions es el criterio de aceptación §8; hacerla ahora no aporta a la implementación y cuesta la descarga. Queda como último paso antes de cerrar Fase 2. |
| D3 | **`youtube_transcript_read` con `start/end` en segundos** (+ `max_chars` como tope) | Coherente con `TranscriptSegment.start/end`, con las citas `&t=620s` de Fase 3 y con cómo se habla de un video ("del minuto 1 al 3"). `max_chars` evita devolver murallas de texto. Offset de caracteres descartado: desconectado del tiempo del video y frágil de convertir. |

- [x] Integrar `yt-dlp`: listar/descargar subtítulos (VTT→segmentos)
      — `services/youtube_subtitles.py` (parser VTT: multi-línea,
      horas opcionales, coma/millis, tags inline, modo rolling para
      auto-captions; `YtDlpSubtitles.list_tracks/fetch` con selección
      manual > auto > prefijo) + fallback en
      `YouTubeService.get_transcript()` (captions → yt-dlp →
      `no_captions`), cacheable con `source=yt_dlp_subtitles`,
      deshabilitable con `enable_subtitle_fallback=False` —
      **108/108 tests offline en verde 23/09/2026**
      (`yt-dlp==2026.8.19` en `requirements.txt`)
- [x] Descarga solo-audio (`bestaudio`, template controlado, temp aislado)
      — `services/youtube_audio.py` (`YtDlpAudioDownloader`: outtmpl
      interna con video_id validado, `mkdtemp` por descarga,
      `FFmpegExtractAudio`→wav 16kHz, `cleanup()` idempotente,
      errores `AudioDownloadFailed`) — 7 tests
      (`tests/test_youtube_audio.py`)
- [x] Instalar FFmpeg (winget/Choco) y `faster-whisper` (`small`, cpu, int8)
      — **FFmpeg 9.0.2** instalado 23/09 vía `winget install Gyan.FFmpeg`;
      `faster-whisper==1.2.1` en `.venv` (+ `requirements.txt`);
      ASR en `services/youtube_asr.py` (`FasterWhisperTranscriber`,
      lazy-load, modelo inyectable, errores `AsrFailed`) — 8 tests
      (`tests/test_youtube_asr.py`). **Smoke real 23/09 PASS**: video
      `jNQXAC9IVRw` → wav 3.5MB/19s → ASR `en` prob 0.95 → cleanup OK
      (smoke con modelo `tiny` solo para validar cableado; producción
      usa `small` — se descarga en el primer job real)
- [x] Tabla `youtube_jobs` en SQLite + worker separado (no solo
      BackgroundTasks: durable, heartbeat, reintentos con backoff)
      — `services/youtube_jobs.py` (idempotente `video_id:lang_key`,
      `claim_next` con `BEGIN IMMEDIATE`, backoff `30s*2^n`, máx 3
      intentos, `reclaim_stale` por heartbeat >15min, `requeue`) +
      `services/youtube_worker.py` (`AsrWorker.run_once/run_forever`,
      stage downloading→transcribing, `duration ≤7200` check,
      errores terminales `duration_exceeded`/`asr_failed`, rate
      limiter compartido con el servicio) — **24 + 13 tests**;
      thread daemon en `mcp_server.main()` (D1, disable con
      `YOUTUBE_WORKER=0`)
- [x] Tools de este servidor: `youtube_transcript_status` + lectura
      paginada (`youtube_transcript_read` con `start/end/max_chars`)
      — en `mcp_server.py`: status por `job_id` o URL (mapea
      pending→processing); read por **segundos** (D3) con `max_chars`
      (mín 1 segmento, flag `truncated`); `youtube_transcript` sin
      captions ahora encola → `{"status":"processing","job_id"}`
      (completed desde caché si el job ya terminó) — caché +
      `get_any()` — **tests en `test_mcp_server.py`/`test_youtube_cache.py`**
- [x] Limpieza automática de audio y temporales + política LRU
      — audio: `cleanup()` en `finally` del worker (también en fallo,
      criterio §8); temporales huérfanos: `sweep_temporals()` (prefijo
      `youtube_transcripts_*`, mtime >1h) en cada iteración de
      `run_forever` — **4 tests sweep + suite worker**
- [x] Verificación: video sin captions → `processing` → `completed`,
      texto en español correcto — **23/09/2026, split en2 evidencias
      reales** (ver LECCIONES entrada "Verificación D2"): (a) trigger
      real `ScMzIvxBSi4` sin captions → job encolado `processing`
      (resultó ser video **sin habla** → `asr_failed` terminal
      correcto); (b) pipeline real job `1m7fTsJzoao` (audio ES) →
      audio8.13MB → `small` → **`Detected language 'es'
      probability1.00`** → texto coherente → `completed` → `read`
      OK → sin temporales. **Fase A agotada**:18/18 videos "last
      hour" ya traen auto-captions (YouTube <1h) — "sin captions +
      habla" ya no se consigue por búsqueda; se documenta como
      limitación, no como deuda de código. **FASE2 CERRADA** ✅

### PRÓXIMA SESIÓN (25/09/2026) — v1 PUBLICADO + template `2026.09.25`
- [x] Fase 4 implementada y verificada (25/09): `TranscriptProvider` +
      circuit breaker + métricas + `youtube_health` + resúmenes
      extractivos + `youtube_transcript_summary` — **334 tests unit
      en verde** + verificación real (`1m7fTsJzoao`); decisiones en
      `docs/DECISIONES.md` (sección Fase 4). **FASE 4 CERRADA** ✅ —
      **v1 funcional completo** (Fases 1-4).
- [x] Publicar: **PR #1 MERGEADO 25/09**
      (https://github.com/seiji142/youtube-transcripts/pull/1,
      `develop → main`, 6 commits, merge `7a3a9c0`) vía
      `.\scripts\gh-publish.ps1 -Merge` — **v1 publicado en `main`**
      por flujo PR (sin commits directos).
- [x] Template migrado a repo `seiji142/gitflow-scaffold` (25/09,
      versión `2026.09.25`): `gh-publish.ps1` con `-Base` (proyecto +
      espejo local), `.ai/commands.md` con validación pre-PR
      (variante B) + Publicación vía script, `.github/workflows/ci.yml`
      adaptado a Python (pytest sin red) — **PR #2 mergeado**
      (https://github.com/seiji142/youtube-transcripts/pull/2,
      merge `f25a61b`, CI `success` en push y PR — primera corrida
      real de CI en verde).
- [x] Check requerido `build` en `main` (25/09): activado por el
      usuario en *Settings → Branches*; **sonda en PR #4**:
      `mergeStateStatus=BEHIND` con CI `in_progress` → `CLEAN` con CI
      `success` (base/head constantes durante la corrida ⇒ el bloqueo
      vino del check; sin modo estricto, verde alcanza).
- [x] Guardar episodios en memoria (`brain_ai_memory_save`) — **hecho**
      tras reiniciar opencode (25/09): Fase 4 (`ep_2139a15e`), Fase 5
      + template (`ep_ea964d67`), gotchas PowerShell/edición/git
      (`ep_23f5956b`). Bridge `brain-ai` restaurado (tools OK).
- Pendientes opcionales:
  - [ ] `master` legacy congelada en `830914e` — borrar cuando el
        flujo esté validado.
  - [ ] Agregar linter **ruff** (step 2 de la variante B en
        `.ai/commands.md`, hoy N/A): config en `pyproject.toml` +
        correrlo pre-commit; al activarlo, actualizar ese paso 2.
- Notas de entorno al arrancar:
  - **Rama:** `develop` (gitflow23/09, template `2026.09.25` desde
    repo GitHub). `main` protegido = PR obligatorio + check `build`
    **activo** (sonda PR #4). `master` legacy congelada en `830914e`.
  - **`gh` autenticado** vía `GH_TOKEN` (PAT fine-grained con los 3
    repos); PRs y merges SIEMPRE por `.\scripts\gh-publish.ps1`
    (regla nueva: nunca `gh pr create/merge` directos).
  - **Tools MCP `brain-ai` restauradas** (reinicio de opencode 25/09):
    memoria/tests/commands OK; episodios de la sesión guardados.

### FASE 3 — Experiencia tipo NotebookLM (RAG)
- [x] Chunking 500-1000 tokens, solapamiento 10-15%, sin cortar frases,
      con timestamps — `services/youtube_chunking.py`
      (`chunk_transcript`: chars/4, greedy por cues, frontera de
      oración best-effort, overlap 12%, cues gigantes → oraciones +
      corte duro con reparto temporal) — **30 tests**
      (`tests/test_youtube_chunking.py`)
- [x] Índice SQLite FTS5 (`transcript_chunks_fts`) —
      `services/youtube_index.py`: tabla normal `transcript_chunks` +
      FTS5 *external content*, `index_transcript` idempotente,
      `ensure_indexed` lazy, búsqueda BM25 filtrada por `video_id`,
      query saneada a literales `OR` — **29 tests**
      (`tests/test_youtube_index.py`)
- [x] Tool `youtube_transcript_search` (`url`, `query`, `top_k`) —
      en `mcp_server.py`: valida URL, `transcript_not_found` con hint
      si no hay transcripción, indexa on-demand, `top_k` 1..20,
      errores estructurados sin crash — **11 tests**
      (`tests/test_mcp_server.py`)
- [x] Respuestas con citas temporales
      (`https://www.youtube.com/watch?v=ID&t=620s`) — `url` por
      resultado con `int(start)` segundos (`test_cita_usa_segundos_...`)
- _Resúmenes jerárquicos para videos largos → **movido a Fase 4**_
      (decisión 25/09, ver `docs/DECISIONES.md`)
- [x] Verificación: preguntar sobre un video largo y recibir fragmentos
      citados, no la transcripción entera — **25/09/2026, video real
      `1m7fTsJzoao` (566s, ASR es en caché)**: 2 chunks indexados
      (903 + 813 tokens, overlap 302.55s < 334.15s), query
      "azulejos" → 1 chunk con cita
      `https://www.youtube.com/watch?v=1m7fTsJzoao&t=8s`, query
      "mermelada naranja" → chunk con `&t=8s`, ningún resultado
      devolvió la transcripción entera (script
      `verify_fase3_search.py`, EXIT=0)
- [x] Suite completa en verde — **263 passed 25/09/2026**
      (error registrado en `docs/LECCIONES.md` 25/09)

### FASE 4 — Resiliencia y operación
- [x] Resúmenes jerárquicos para videos largos
      (movidos desde Fase 3) — `services/youtube_summarize.py`:
      extractivo TF-IDF sin LLM (offline), secciones temporales +
      overall, tool `youtube_transcript_summary` con citas `&t=` —
      **22 tests** + verificación real `1m7fTsJzoao` (3 secciones +
      overall, EXIT=0)
- [x] Interfaz `TranscriptProvider` (`YouTubeTranscriptApiProvider`,
      `YtDlpSubtitleProvider`, `FasterWhisperProvider`,
      `ExternalAsrProvider` stub deshabilitado) con enable/disable
      por config — `services/youtube_providers.py`; servicio
      reescrito sobre la interfaz sin cambiar su API pública —
      **24 tests** (`tests/test_youtube_providers.py`)
- [x] Circuit breaker + backoff con jitter tras 429 — **red de
      seguridad**, no prevención primaria (la prevención es el
      RateLimiter de Fase 1, ver §4 incidente 429) —
      `services/youtube_breaker.py` (umbrales 5 fallos/60s →
      cooldown 300s ±20%; `NoCaptionsAvailable` cuenta como éxito;
      backoff de jobs sigue determinista a propósito) + tool
      `youtube_health` (proveedores, breakers, métricas) —
      **33 tests** (`tests/test_youtube_breaker.py` + `TestHealthTool`)
- [x] Métricas por proveedor + endpoint de salud — `ProviderMetrics`
      (calls/success/empties/failures/rejected/último error) +
      `youtube_health`; worker ASR con breaker propio compartiendo
      métricas — verificación real: breakers `closed`
- [x] Tests de integración periódicos con videos públicos fijos —
      sin CI en el repo: corrida manual periódica
      `.venv\Scripts\python -m pytest tests/test_integration.py -m integration`
      (8 tests, skip diseñado ante bloqueo 429, ver LECCIONES 21/09)
- [x] Cuotas por usuario, concurrencia máxima, retención documentada —
      monousuario local: RateLimiter 1s/10-por-60s compartido
      servicio+worker; worker 1 job a la vez; videos ≤2h;
      caché SQLite TTL 7 días (`data/`, gitignored); sin autenticación
      ni multiusuario en v1
- [ ] Documentar decisión en memoria (`brain_ai_memory_save`) —
      **bloqueado esta sesión**: bridge MCP `brain-ai` caído (sin
      tools de memoria/tests); reintentar al reiniciar opencode

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
yt-dlp==2026.8.19                # Fase 2 (subtítulos + audio)
faster-whisper==1.2.1            # Fase 2 (ASR local)
FFmpeg 9.0.2 (sistema, winget)   # Fase 2 (audio→wav) — Gyan.FFmpeg
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

- [x] Video ES con captions → transcripción en <10s vía servidor MCP propio
      — suite integración 8/8 verde (22/09/2026), verificado con red real
- [x] Video EN con captions → transcripción con idioma detectado
      — suite integración 8/8 verde (22/09/2026), verificado con red real
- [x] Video sin captions → job async → transcripción local correcta
      — **Fase 2 (23/09)**: trigger real (`ScMzIvxBSi4` →
      `processing`) + pipeline real (`1m7fTsJzoao` → `completed`,
      `es` prob1.00, texto coherente); ver checkbox de verificación
      §5 Fase 2 para el split de evidencias
- [x] Video largo → `search` devuelve chunks citados con `&t=`
      — **Fase 3 (25/09)**: video real `1m7fTsJzoao` (566s) → 2
      chunks (903/813 tokens) con citas `&t=8s`, sin transcripción
      entera; ver checkbox de verificación §5 Fase 3
- [x] Repetir mismo video usa caché (sin re-extracción)
      — tests unit + demo `data/probe.db`
- [x] URL inválida / video privado / playlist → error claro, sin crash
      — 35 tests parser + 6 tests errores
- [x] Audio temporal siempre eliminado tras ASR
      — **Fase 2**: `cleanup()` en `finally` del worker + sweep de
      huérfanos; unit tests + corrida real verificada "sin
      temporales" (23/09)
- [x] brain-ai-01 no modificado en Fase 1
- [x] Proveedor bloqueado repetido → breaker abre y la llamada falla
      rápido (`provider_unavailable`); `youtube_health` refleja
      breakers y métricas
      — **Fase 4 (25/09)**: 5 fallos/60s → cooldown 300s ±20%;
      tests `TestServicioConBreaker` + verificación real (breakers
      `closed`)
- [x] Video con transcripción → `summary` devuelve secciones +
      overall citados con `&t=`, no la transcripción entera
      — **Fase 4 (25/09)**: extractivo TF-IDF sin LLM; verificación
      real `1m7fTsJzoao` (3 secciones + overall con citas)

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
