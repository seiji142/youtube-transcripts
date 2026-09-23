# Lecciones aprendidas

Registro de errores reales y su resolución, para no repetirlos.
Regla de obligatorio cumplimiento: ver `.ai/rules.md` §10.

## Template de entrada

```markdown
## YYYY-MM-DD — Título corto del incidente

**Tipo:** A (error duro) | B (warning) | C (cambio de plan)
**Comando:** `comando exacto que falló`
**Error/Warning:** (tal cual, sin parafrasear)
**Causa raíz:** (con evidencia, no suposición)
**Fix:** (qué se cambió)
**Verificación:** (re-comando o suite en verde)
**Lección:** (regla derivada, si aplica)
```

---

## 2026-09-23 — Smoke ASR: Python 3.10 deprecado para huggingface_hub

**Tipo:** B (warning relevante — deprecation)
**Comando:** `.venv\Scripts\python C:\...\smoke_asr.py`
**Error/Warning:** `Deprecated Feature: Support for Python version 3.10 has been deprecated. Please update to Python 3.11 or above`
**Causa raíz:** `huggingface_hub` (dependencia de `faster-whisper`) marca EOL de soporte para Python 3.10; el venv del proyecto usa 3.10.7 (fijado en TAREAS §7). Verificado en la primera descarga de modelo del smoke 23/09.
**Fix:** Ninguno aún — es warning, no error (smoke PASS). Trackear: migrar el proyecto a Python ≥3.11 cuando salga de v1 o cuando un upgrade de dependencia lo exija.
**Verificación:** smoke completo en verde pese al warning; suite 123/123.
**Lección:** Las próximas versiones de `huggingface_hub` pueden dejar de soportar 3.10 del todo; al actualizar `faster-whisper` verificar primero compatibilidad con la versión de Python del venv.

---

## 2026-09-23 — Warnings de HuggingFace Hub en Windows (symlinks + sin token)

**Tipo:** B (warning relevante — primera descarga de modelo)
**Comando:** `.venv\Scripts\python C:\...\smoke_asr.py`
**Error/Warning:**
1. `UserWarning: huggingface_hub cache-system uses symlinks by default ... your machine does not support them in C:\Users\seiji\.cache\...` (x2, modelos)
2. `Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.`
**Causa raíz:** (1) Windows sin Developer Mode ni admin no puede crear symlinks → HF usa copia plana (más disco, funciona igual). (2) Descarga anónima: rate limit más bajo, sin HF_TOKEN (correcto: no queremos secrets en el proyecto — solo aplica si algún día la descarga se torna lenta/bloqueada, usar env var del SO, nunca commitear).
**Fix:** Ninguno requerido — degradación solo de performance/espacio, no de funcionalidad. Podría desactivarse el warning con `HF_HUB_DISABLE_SYMLINKS_WARNING=1` si molesta en logs.
**Verificación:** descarga del modelo `tiny` completada, smoke PASS, temporal limpio.
**Lección:** En Windows sin Developer Mode, esperar cache HF plana en `~/.cache/huggingface`; no confundir con error. Para rate limits de HF en CI/uso intensivo, usar `HF_TOKEN` vía entorno, nunca hardcodear.

---

## 2026-09-23 — Runner async sin salida: `'NoneType' object is not subscriptable`

**Tipo:** A (comando terminó con status=error, stdout=null, returncode=null)
**Comando:** `.venv\Scripts\python C:\...\verify_d2_v3.py` (vía `run_command` async)
**Error/Warning:** `'NoneType' object is not subscriptable` (stderr, sin traceback completo, stdout vacío)
**Causa raíz:** **No determinada** con la evidencia disponible: la re-ejecución **síncrona idéntica** del mismo script corrió completo (imprimió `[1/2]...` y terminó con el FAIL esperado del script, exit1). No se reprodujo. Sospecha sin confirmar: fallo de captura del wrapper async, no del script.
**Fix:** Re-ejecutar comandos de verificación largos de forma síncrona (bash directo) cuando el runner async devuelva salida vacía.
**Verificación:** misma v3 síncrona → output completo y consistente.
**Lección:** stdout=null + returncode=null + error críptico = no confiar en el diagnóstico del runner async; re-ejecutar sincrónico antes de diagnosticar el script.

---

## 2026-09-23 — Timeout120s por procesar resultados de búsqueda sin `extract_flat`

**Tipo:** A (shell tool terminó el comando por timeout)
**Comando:** probe de `results?search_query=...` con `YoutubeDL` **sin** `extract_flat`
**Error/Warning:** `shell tool terminated command after exceeding timeout120000 ms`
**Causa raíz:** `extract_info(url)` sobre la página de resultados (~487 entradas) con el default `extract_flat=False` intentó **extraer cada video por completo** (una request por entrada). Evidencia: la misma URL con `extract_flat='in_playlist'` respondió en segundos.
**Fix:** Siempre `extract_flat='in_playlist'` para páginas/playlist de búsqueda; extraer completo solo los pocos IDs elegidos (con gap ≥1.3s).
**Verificación:** re-run con flat →3 candidatos en <5s.
**Lección:** En yt-dlp, hojas de búsqueda/listas grandes = flat primero, nunca procesamiento completo en cascada.

---

## 2026-09-23 — `ytsearchdate10:` ya no existe en yt-dlp2026.8.19

**Tipo:** A (error duro — exit≠0)
**Comando:** `ydl.extract_info('ytsearchdate10:vlog español', download=False)`
**Error/Warning:** `yt_dlp.networking.exceptions.NoSupportingHandlers: Unable to handle request: Unsupported url scheme: "ytsearchdate10" (requests, urllib)`
**Causa raíz:** En `yt-dlp==2026.8.19` los extractores YouTube de búsqueda disponibles son solo `youtube:search` (`ytsearchN:`) y `youtube:search_url` (URL `results?...`). **No existe** `youtube:search:date` (verificado enumerando `gen_extractor_classes()`), por lo que el prefijo `ytsearchdateN:` cae al extractor `generic` y falla por scheme.
**Fix:** Usar `ytsearchN:query` (relevancia) o una URL `https://www.youtube.com/results?search_query=...&sp=<filtro>` vía `youtube:search_url`.
**Verificación:** `ytsearch2:vlog espanol` →2 entradas OK; URL `results` →487 OK.
**Lección:** No asumir sintaxis históricas de yt-dlp entre versiones grandes; verificar IE_NAMEs disponibles antes de construir queries de búsqueda.

---

## 2026-09-23 — Verificación D2 exit1: job `asr_failed` "no produjo segmentos"

**Tipo:** A (verificación con exit≠0)
**Comando:** `.venv\Scripts\python C:\...\verify_d2_asr.py` (video `ScMzIvxBSi4`)
**Error/Warning:** `status=failed ... error=asr_failed`; job en DB: `El ASR no produjo segmentos (audio vacío o sin habla)`
**Causa raíz:** El video de prueba **no tiene habla** — evidencia del diagnóstico posterior: título real `'Placeholder Video'` (94s), `volumedetect mean=-15.9dB` (audio audible), `vad_filter=True →0 segmentos`, `vad_filter=False →14 segmentos` todos `" ."` (ruido), `language_probability≈0.36`. **No es bug del pipeline**: modelo `small` cargó (483MB), audio descargó (18MB wav), inferencia corrió y clasificó correctamente "sin habla" como error terminal.
**Fix:** (1) Candidato nuevo vía búsqueda de videos frescos sin captions — **agotado**:18/18 videos de "last hour" ya traen auto-captions (YouTube las genera en <1h). (2) Fallback controlado: job manual `1m7fTsJzoao` (audio español real) → **worker completed, `Detected language 'es' probability1.00`, texto coherente, sin temporales**. El trigger "sin captions → processing" ya estaba probado con `ScMzIvxBSi4` en corrida real.
**Verificación:** `verify_d2_v4.py` → `VERIFY PASS (fase-B)`, EXIT=0.
**Lección:** Un "video sin captions" de tests no garantiza habla; verificar siempre habla/volumen antes de usarlo para validar ASR. La rapidez de auto-captions de YouTube (2026) hace casi inviable hallar "sin captions + habla" por búsqueda — el trigger y el pipeline se validan por separado.

---

## 2026-09-23 — Ternario `? :` no existe en PowerShell 5.1

**Tipo:** A (error duro — parse error del shell)
**Comando:** `comando de verificación de entorno con (Get-Command winget ...) ? "OK" : "NOT FOUND"`
**Error:** `Token '?' inesperado en la expresión o la instrucción... ParserError`
**Causa raíz:** El operador ternario condicional (`? :`) es sintaxis de PowerShell 7+. El shell del entorno es Windows PowerShell 5.1 (`$PSVersionTable` → 5.1); falla en *parse*, antes de ejecutar cualquier comando.
**Fix:** Usar `if / else` clásico o el operador binario `$(...) -and` / `-ne $null` para ramificar.
**Verificación:** comando re-escrito con `if ($wg) { ... } else { ... }` ejecutado sin errores (ffmpeg/winget/choco detectados correctamente).
**Lección:** En este entorno asumir PowerShell 5.1: prohibido ternario `? :`, `??`, `&&`/`||` de pipeline. Encadenar con `;` y `if ($?)` o `if/else`.

---

## 2026-09-23 — Comando `file` no existe en PowerShell (Windows)

**Tipo:** A (error duro — exit del comando)
**Comando:** `file .ai/rules.md docs/LECCIONES.md`
**Error:** `file : El término 'file' no se reconoce como nombre de un cmdlet... CommandNotFoundException`
**Causa raíz:** `file` es una utilidad de Unix/macOS; no está en PATH de Windows PowerShell 5.1. Verificado con `Get-Command file` → no encontrado.
**Fix:** Usar alternativas nativas de Windows/Python:
- `git ls-files --eol <archivo>` → muestra EOL del index y worktree
- `python -c "p=open(f,'rb').read(); p.count(b'\\r\\n')"` → cuenta CRLF/LF
**Verificación:** `git ls-files --eol .ai/rules.md` → `i/lf w/crlf` (confirmado).
**Lección:** En win32, no asumir utilidades Unix (`file`, `grep`, `cat`). Usar cmdlets de PowerShell o binarios del proyecto (git, python).

---

## 2026-09-23 — Warning CRLF de git al hacer `git add`

**Tipo:** B (warning relevante)
**Comando:** `git add .ai/rules.md docs/LECCIONES.md`
**Error/Warning:** `warning: LF will be replaced by CRLF in .ai/rules.md.` (y lo mismo para `docs/LECCIONES.md`)
**Causa raíz:** `core.autocrlf=true` en este repo (Windows). Git guarda LF en el index (`i/lf`) y convierte a CRLF en el worktree (`w/crlf`). Los archivos se escriben con CRLF en disco; al add, git normaliza a LF para el repo. **No es un error de contenido**, es conversión de fin de línea esperada en Windows.
**Fix:** No hizo falta fix de código — es comportamiento deseado de `autocrlf=true`. Se verificó con `git ls-files --eol` que index=LF y worktree=CRLF.
**Verificación:** `git ls-files --eol .ai/rules.md docs/LECCIONES.md` → ambos `i/lf w/crlf`; tests 108/108 en verde tras el commit.
**Lección:** Los warnings `LF will be replaced by CRLF` con `autocrlf=true` son **informativos**, no rompen nada. No "arreglar" convirtiendo archivos a LF a mano (rompería el worktree Windows). Solo investigar si el diff muestra cambios de EOL no deseados en archivos que no tocaste.

---

## 2026-09-23 — Regex monolítica rompió la collection de tests

**Tipo:** A (error duro — collection de pytest falló)
**Archivo:** `services/youtube_subtitles.py`
**Comando:** `.venv\Scripts\python -m pytest tests/ -m "not integration" -q`
**Error:** `re.error: missing ), unterminated subpattern at position 52`

### Qué pasó

Se escribió una regex compleja (`_CUE_BLOCK_RE`) para capturar bloques
VTT completos (timing + multi-línea) con un solo `re.finditer`.
Los paréntesis de grupos anidados quedaron desbalanceados.

### Por qué fue grave

`re.compile()` valida el patrón **al importar el módulo**. Cualquier
test que importara `youtube_service` (directa o vía `mcp_server`)
fallaba en *collection*, antes de correr un solo test: 4 archivos
de test inutilizados por una línea rota.

### Por qué no se "arregló el paréntesis"

La regex era frágil por diseño:

- Mezclaba directivas (`NOTE`/`STYLE`) y cues multi-línea
- Lookaheads `(?!...)` difíciles de razonar
- Cualquier VTT real de YouTube la rompía de formas distintas

### Solución

State machine simple `_iter_cue_blocks()`:

1. Recorre línea por línea
2. Acumula hasta un blanco o directiva conocida
3. Devuelve bloques crudos
4. Cada bloque se parsea con regex chica solo para el timing (`_TIMING_RE`)

Mismo comportamiento, ~30 líneas legibles. Cubierto por fixtures
(multi-línea, rolling, tags inline, coma/millis, sin horas).

### Regla derivada

> **No usar regex monolíticas para parsers de formato con bloques
> multi-línea.** Preferir state machine línea-por-línea + regex
> pequeña solo para el token crítico. Si el parser vive en un
> módulo importado por tests, una regex rota rompe la *collection*
> completa, no solo sus tests.
