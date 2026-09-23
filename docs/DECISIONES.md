# Decisiones por fase — historial

Registro estructurante del proyecto: **qué se decidió, por qué y con qué
evidencia**, fase por fase. Complementa (no duplica):

- `docs/TAREAS_YOUTUBE.md` → plan operativo, checkboxes y criterios.
- `docs/LECCIONES.md` → errores de shell/warnings y sus fixes (§10 de rules).
- `docs/investigacion-youtube/` → investigación externa de partida.

Orden cronológico inverso (más reciente arriba).

---

## Setup Gitflow (23/09/2026)

| Decisión | Por qué | Evidencia |
|----------|---------|-----------|
| **Flujo `develop` / `main` / `feature/*`** (plantilla `templates/gitflow-scaffold`) | `main` = producción protegida (PR obligatorio, SIN "Require approvals": en repo personal el autor no puede aprobar su propio PR); `develop` = trabajo diario; `feature/*` = tareas grandes. Resuelve la tensión con la regla "nunca commitear directo a main/master": los commits van a develop/features y la regla se cumple al pie de la letra | Checklist en `docs/gitflow-scaffold.md`; `develop` creada desde `origin/main@830914e` y con tracking (23/09) |
| **Q1: omitir `deploy.yml` / GitHub Pages** | Este repo es Python/MCP: no hay `package.json`, `npm build` ni `dist` — el workflow del template (npm/vite) no aplica. Si en el futuro hay sitio estático (docs), se retoma el template | Revisión del repo: solo `requirements.txt`, sin build frontend |
| **Q2: `master` legacy congelada en `830914e`** | `main` nació con el mismo tip → mismo contenido, cero pérdida. `master` queda como histórico hasta validar el flujo; se borra después | `git ls-remote`: `refs/heads/main` = `refs/heads/master` = `830914e` |
| **Q3: bash para checkout/creación de ramas** | Las tools MCP `git_*` no tienen creación/checkout de ramas; el propio template prescribe `git checkout -b` con bash. Codificado como excepción en `rules.md` (§9) y `system.md` (tabla Git) | Setup de `develop` ejecutado con bash autorizado (23/09) |
| **`opencode.json` del template no se copia** | El del proyecto ya es el template con placeholders resuelto (+ provider groq + server `youtube-transcripts`) | Comparación línea por línea 23/09 |
| **Lección: `git_subir_cambios(rama=X)` no crea la rama** | La tool hace add+commit en la rama **actual** y `rama` solo apunta el push; con rama inexistente: commit local + push fallido | LECCIONES.md "git_subir_cambios(rama=...)" (fix: re-intento sin `rama`) |

---

## FASE 2 — Fallback real / ASR (23/09/2026)

| Decisión | Por qué | Evidencia |
|----------|---------|-----------|
| **Parser VTT con state machine, no regex monolítica** | `_CUE_BLOCK_RE` con grupos anidados quedó desbalanceada → `re.error` al importar y rompía la *collection* completa de pytest (4 archivos de test inutilizados). State machine línea-por-línea + regex chica solo para timing | LECCIONES.md "Regex monolítica rompió la collection" |
| **FFmpeg 9.0.2 (winget `Gyan.FFmpeg`) + `faster-whisper==1.2.1` pineado** | Reproducibilidad; FFmpeg convertía audio→wav16k como postprocesador yt-dlp; versión fija en `requirements.txt` (regla de calidad) | Instalación verificada 23/09; suite en verde |
| **Audio: `bestaudio` + outtmpl interna + `mkdtemp` aislado + wav 16 kHz** | Regla §3: el usuario **no** controla rutas de salida ni flags de yt-dlp; temp aislado por descarga + `cleanup()` idempotente; wav16k = formato canónico para ASR | `services/youtube_audio.py` + 7 tests |
| **ASR `small`/`cpu`/`int8` con lazy-load e inyección de modelo** | Plan Fase 2; lazy evita cargar460 MB al importar; modelo inyectable = tests sin red ni descargas | `services/youtube_asr.py` + 8 tests |
| **Smoke con `tiny` antes que `small`** | Validar cableado real (FFmpeg + av + inferencia) bajando75 MB en vez de460 MB | Smoke `jNQXAC9IVRw`: `en` prob0.95, PASS |
| **D1: worker = thread daemon dentro de `mcp_server` + tabla `youtube_jobs` durable** | Un solo proceso que operar en Windows; SQLite hace el estado durable (crash → `pending`/`processing` recuperado por `reclaim_stale` con heartbeat >15 min); `BackgroundTasks` descartado (no durable). Jobs idempotentes `video_id:lang_key`, backoff `30s*2^n` máx3 intentos | TAREAS §5 tabla D1; 24 tests JobStore + 13 worker |
| **D2: verificación ASR real en split de2 evidencias** | El video de prueba `ScMzIvxBSi4` resultó **sin habla** ("Placeholder Video") → `asr_failed` terminal **correcto**. Búsqueda de "sin captions + habla" **agotada**:18/18 videos de última hora ya traen auto-captions de YouTube (generan en <1h en2026). Split: (a) trigger real → `processing`; (b) pipeline real `1m7fTsJzoao` → `es` prob **1.00**, texto coherente, sin temporales | TAREAS §5 checkbox verificación; LECCIONES "Verificación D2"; run `verify_d2_v4.py` EXIT=0 |
| **D3: `youtube_transcript_read` con `start/end` en SEGUNDOS (+ `max_chars`)** | Coherente con `TranscriptSegment.start/end` y con las citas `&t=620s` de Fase3; `max_chars` evita murallas de texto (mínimo1 segmento). Offset de caracteres descartado: desconectado del tiempo, frágil de convertir | TAREAS §5 tabla D3; tests de rango/truncado |
| **`youtube_transcript` sin captions → encola y devuelve `processing`** | El criterio §8 pide job async; el cambio vive solo en la capa MCP (el servicio sigue lanzando `NoCaptionsAvailable`) → tests de Fase 1 intactos | `mcp_server._enqueue_asr` + tests encola/idempotencia |
| **Errores terminales vs reintentables** | `duration_exceeded` y `asr_failed` (sin habla) no se reintentan (un reintento no los arregla); fallos de red/bloqueo sí, con backoff. Rate limiter **compartido** servicio/worker (prevención429 del incidente21/09) | Tests de worker: terminal vs pending |
| **Audio limpiado en `finally` + sweep de huérfanos >1h** | Criterio §8 "audio siempre eliminado tras ASR" — también en fallo; sweep cubre crashes (dirs `youtube_transcripts_*`) | Tests sweep + corrida real "sin temporales" |

---

## FASE 1 — MVP captions (21-22/09/2026)

| Decisión | Por qué | Evidencia |
|----------|---------|-----------|
| **Servidor MCP propio (`mcp_server.py`), no registrar tools en `brain-ai-01/mcp_bridge.py`** | Consumidores distintos: no todos necesitan ambos proyectos; acoplar obligaría a cargar dependencias no usadas. Repo autocontenido | TAREAS §3.1; memoria del episodio |
| **Pipeline escalonado captions → yt-dlp → faster-whisper → ASR externo opcional** | 100% gratis sin API keys obligatorias; el primero que tenga éxito gana; ASR externo solo adaptador opcional | TAREAS §3.2; investigación externa convergente |
| **`youtube-transcript-api` v1.x (`fetch()`), no legacy0.6.x** | El legacy (`list_transcripts` + `TextFormatter`) no devuelve segmentos con timestamps útiles | TAREAS §4 "Descartado y por qué" |
| **SQLite (caché + jobs + FTS5 futuro), sin servidor externo** | Ventaja "100% gratis/offline"; sin Redis/PostgreSQL; `data/` gitignored | Caché `data/youtube.db`, TTL7d |
| **Errores tipados ANTES del parser de URLs** | `youtube_errors.py` creado primero para que el parser lance errores con `code` estable desde el inicio (jerarquía `TranscriptError` +4 subclases) | Memoria episodio "Paso2 Fase1";6 tests |
| **RateLimiter preventivo (1s mín entre requests + máx10/60s)** | Incidente429 (21/09): sondeo de~25 videos en ráfaga → `IpBlocked`. YouTube no publica umbral; consenso comunidad ≥1s. Prevención primaria (circuit breaker queda para Fase4) | TAREAS §4 incidente;9 tests + integración |
| **Tests de integración con videos fijados + `skip` ante bloqueo persistente** | El429 es ambiental (rate limit), no bug del código; suite no debe fallar por eso | Suite integración **8/8** en verde22/09 tras levantarse el bloqueo |
| **Diseño por fases (1→4), valor desde Fase1** | MVP usable (captions) antes de complejizar (ASR/RAG/resiliencia) | TAREAS §5 |

---

## FASE 3 — RAG / experiencia NotebookLM (prevista, sin decidir)

Secciones abiertas — se rellenan al arrancar la fase:

- _Chunking:_ 500-1000 tokens, solapamiento10-15%, sin cortar frases, con timestamps (criterio del plan; pendiente elegir estrategia exacta).
- _Índice:_ SQLite FTS5 `transcript_chunks_fts`.
- _Tool:_ `youtube_transcript_search` con citas `https://www.youtube.com/watch?v=ID&t=620s`.
- _Decisiones pendientes:_ tamaño óptimo de chunk medido con videos reales; si resúmenes jerárquicos van en Fase3 o4.

## FASE 4 — Resiliencia y operación (prevista, sin decidir)

- _Interfaz `TranscriptProvider`_ con enable/disable por config.
- _Circuit breaker + backoff con jitter_ tras429 — red de seguridad, no prevención (esa es el RateLimiter de Fase1).
- _Métricas por proveedor + endpoint de salud_; cuotas, concurrencia, retención.
- _Decisiones pendientes:_ umbrales del breaker; si ASR externo opcional entra en v1.
