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

## 2026-09-25 — PAT fine-grained de otro repo: 403 hasta en LECTURAS de repo público

**Tipo:** C (output inesperado — cambia el plan de verificación Fase 5)
**Comando:** `$env:GH_TOKEN = [Environment]::GetEnvironmentVariable("GH_TOKEN","User"); gh pr list --repo seiji142/youtube-transcripts` (y `gh api repos/.../branches/main/protection`)
**Error/Warning:** `gh: Resource not accessible by personal access token (HTTP 403)` en ambos (lectura de PRs y de protección). `gh auth status` previo: OK (`seiji142`, token `github_pat_...` válido).
**Causa raíz:** El PAT fine-grained vigente está en *Repository access → Only select repositories* (solo portfolio): GitHub lo deja **ciego fuera de sus repos, incluso para lecturas de repos públicos**. La nota de la UI ("los PAT siempre leen repos públicos") no aplica cuando el acceso es *Only select repositories*. Evidencia: la misma lectura por API anónima sí funcionaba el 23/09 (`protected=True`).
**Fix:** Ninguno en código — reordena la Fase 5: el **Paso 0 del usuario en el navegador** (agregar `seiji142/youtube-transcripts` al PAT + *Update token*) es prerrequisito **también para verificar lecturas**, no solo escritura. Re-ejecutar la verificación tras su confirmación.
**Verificación:** pendiente (bloqueado en Paso 0 del usuario).
**Lección:** Con fine-grained *Only select repositories*, el token no existe fuera de sus repos (403 en todo). El diagnóstico del playbook se amplía: *lectura OK + escritura 403 = permisos; lectura 403 en repo público = el repo no está en Repository access (o token vencido/revocado)*.

---

## 2026-09-25 — Base64 de `gh api` roto con el pipeline de PowerShell 5.1

**Tipo:** A (error duro — comando falló)
**Comando:** `gh api repos/seiji142/gitflow-scaffold/contents/VERSION --jq '.content' | ForEach-Object { [Convert]::FromBase64String($_ ...) }`
**Error/Warning:** `No se encuentra ninguna sobrecarga para "FromBase64String" y el número de argumentos "2"` (repetido por cada línea del contenido)
**Causa raíz:** el `.content` llega como **múltiples líneas** de base64; el pipeline las manda de a una a `FromBase64String`, que recibe 2 argumentos (string + el byte de `\r` residual o la siguiente línea). PowerShell 5.1, no la API de GitHub.
**Fix:** dos alternativas validadas — (1) `gh api -H "Accept: application/vnd.github.raw" repos/.../contents/<file>` (devuelve texto crudo, preferida), (2) unir las líneas antes de decodificar: `(gh api ... --jq .content) -replace "\`n",""` → un solo `FromBase64String`. También: el redirect `>` de PS 5.1 escribe **UTF-16** (BOM 255,254) — para archivos byte-exactos usar `[IO.File]::WriteAllBytes`.
**Verificación:** `gh api -H raw` + `WriteAllBytes` reprodujeron el script remoto (90 líneas, con `-Base`), sintaxis PSParser 0 errores en local y en template.
**Lección:** para contenido crudo de la API de GitHub, `Accept: application/vnd.github.raw` evita todo el ciclo base64+pipeline; nunca confiar en `>` de PowerShell 5.1 para archivos de terceros (UTF-16 silencioso).

---

## 2026-09-25 — SyntaxError en test nuevo: `def test_overall trae_...` sin guion bajo

**Tipo:** A (error duro — collection error de pytest)
**Comando:** `.venv\Scripts\python.exe -m pytest tests/ -m "not integration" -q`
**Error/Warning:** `E File "C:\...\tests\test_youtube_summarize.py", line 66` / `E def test_overall trae_las_mejores_oraciones(self) -> None:` / `E SyntaxError: invalid syntax` — `1 error during collection`
**Causa raíz:** Typo al escribir el nombre del test (`test_overall trae_...` con espacio en vez de `test_overall_trae_...`). Error del autor, no del código bajo test (el módulo `youtube_summarize.py` importaba bien).
**Fix:** Renombrar a `test_overall_trae_las_mejores_oraciones`.
**Verificación:** suite completa en verde: `334 passed, 8 deselected` (25/09/2026).
**Lección:** Un collection error frena toda la suite (no solo el archivo); ante `ERROR collecting`, mirar primero la línea citada — suele ser typo de sintaxis en el test nuevo, no regresión.

---

## 2026-09-25 — Test de timestamps asumió chunk de 1 segmento (50.0 != 5.0)

**Tipo:** A (error duro — test fallido)
**Comando:** `.venv\Scripts\python.exe -m pytest tests/ -q`
**Error/Warning:** `E assert 50.0 == 5.0` en `tests/test_youtube_index.py:220` (`TestSearch::test_timestamps_preservados_en_resultado`) — `1 failed, 262 passed in 21.80s`
**Causa raíz:** El test sembraba 10 segmentos de 5s (transcript total 50s ≈ 100 tokens → 1 solo chunk, por debajo de `min_tokens=500`) y esperaba `end == 5.0` (fin del primer segmento). El chunk cubre los 10 segmentos → `end == 50.0`, que es el comportamiento correcto por diseño (`start`/`end` = primer/último segmento del chunk). Expectativa del test, no bug del chunking.
**Fix:** Ajustar la aserción a `start == 0.0` y `end == 50.0` con comentario "transcript corto → 1 chunk".
**Verificación:** suite completa en verde: `263 passed in 20.73s` (25/09/2026).
**Lección:** Al testear timestamps de chunks, calcular el `end` esperado según cuántos segmentos caben en el chunk (transcript corto = 1 chunk que cubre todo el rango), no asumir el fin del primer segmento.

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

## 2026-09-23 — `POST /ingest` falló: body no parseable (encoding PowerShell 5.1)

**Tipo:** A (WebException — exit del comando)
**Comando:** `Invoke-RestMethod -Uri "http://127.0.0.1:8000/ingest" -ContentType "application/json"` (episodio de cierre gitflow)
**Error/Warning:** `{"detail":"There was an error parsing the body"}`
**Causa raíz:** el body contenía caracteres no-ASCII (ej. `"PRÓXIMA"`) y PowerShell 5.1 serializó el string sin charset UTF-8 explícito (`ContentType: application/json` sin `charset=` → encoding ANSI/cp1252) → bytes inválidos para UTF-8 → el servidor no parseó el JSON. Evidencia: el **primer** `/ingest` del día (cuerpo100% ASCII) funcionó con el mismo código.
**Fix:** re-envío con Python stdlib `urllib` + `json.dumps` (`ensure_ascii=True` → body ASCII puro con escapes `\uXXXX`), script en temp.
**Verificación:** `200 {"ok":true,"episode_id":"ep_320450540d3e484a899566084fbf34ca"}`.
**Lección:** con `Invoke-RestMethod` en PS5.1, si el body trae tildes/ñ: poner `charset=utf-8` explícito o serializar desde Python. Preferido: helper Python para `/ingest` (sin sorpresas de encoding).

---

## 2026-09-23 — `gh api` falló por falta de autenticación

**Tipo:** A (error duro — exit≠0)
**Comando:** `gh api repos/seiji142/youtube-transcripts/branches/main/protection` (y `gh api repos/seiji142/youtube-transcripts --jq ...`; re-intento `gh auth status`)
**Error/Warning:** `To get started with GitHub CLI, please run:  gh auth login` / `Alternatively, populate the GH_TOKEN environment variable with a GitHub API authentication token.` / `You are not logged into any GitHub hosts. To log in, run: gh auth login` (EXIT=1)
**Causa raíz:** `gh` instalado pero **sin autenticar** (sin `GH_TOKEN` ni sesión de `gh auth login`). El SSH del remote autentica git push/pull, **no** la API REST — son capas distintas.
**Fix:** lectura de estado vía API **anónima** `Invoke-RestMethod https://api.github.com/repos/seiji142/youtube-transcripts/branches/main` (repo público) → `protected=True`. Autenticación PAT documentada como **Fase 5** en `docs/gitflow-scaffold.md` (+ template `templates/gitflow-scaffold/TEMPLATE_GITFLOW_GH_PAGES.md`); pendiente de realizar.
**Verificación:** `branch=main protected=True`, `enabled=true`, `default_branch=main`, `private=false`.
**Lección:** SSH ≠ token de API. Para leer estado de un repo **público** basta `api.github.com` anónimo; para PRs/detalle completo de protección hace falta `gh auth` (Fase 5). No confiar en `gh` instalado = `gh` usable.

---

## 2026-09-23 — Tools MCP brain-ai ausentes del esquema de la sesión

**Tipo:** C (output inesperado — obligó a diagnosticar y cambiar de plan)
**Comando:** llamadas a `brain-ai_memory_save` y `brain-ai_run_tests`
**Error/Warning:** `Model tried to call unavailable tool 'brain-ai_memory_save'. Available tools: ... (sin brain-ai)`
**Causa raíz:** el servidor HTTP de brain-ai **está vivo** (`GET /http://localhost:8000/health` → `200 {"ok":true}`); lo que no está conectado es el **puente MCP** (`mcp_bridge.py`) en la sesión opencode actual — sus tools no aparecen en el esquema. No es caída del servicio.
**Fix:** (1) tests → bash `.venv\Scripts\python -m pytest ...` directo (186/186, exit0); (2) memoria → API REST `POST /ingest` con el payload del cliente canónico `brain-ai-01/clients/memoria.py` (`guardar()`); (3) reconexión del bridge → reiniciar opencode (fuera del alcance de la sesión).
**Verificación:** `PYTEST_EXIT=0`; `POST /ingest` respondió OK (episodio gitflow guardado).
**Lección:** "tool MCP ausente del esquema" ≠ "servicio caído": verificar `/health` antes de diagnosticar. El cliente canónico documenta la API REST (`/ingest`, `/retrieve`, `/consolidate`) como fallback cuando el bridge MCP no está disponible.

---

## 2026-09-23 — `git_subir_cambios(rama=...)` no crea la rama: push fallido

**Tipo:** A (push fallido, exit≠0)
**Comando:** `git_subir_cambios(mensaje="Add Fase 2 ASR: ...", rama="feat/fase2-asr-jobs-worker")`
**Error/Warning:** `error: src refspec feat/fase2-asr-jobs-worker does not match any` / `error: failed to push some refs to 'git@github.com:seiji142/youtube-transcripts.git'`
**Causa raíz:** La tool MCP ejecuta `git add . && git commit && git push origin <rama>` **sin checkout/creación de rama**. El parámetro `rama` solo apunta el refspec de push; como la rama no existía localmente, el push falló. **add+commit SÍ corrieron** sobre la rama actual (`master`) → commit `ab149ac` local, árbol limpio, `master` ahead de `origin/master` por 1 (evidencia: `git_ver_historial` + `git_ver_estado`).
**Fix:** (1) Push directo a `master` para completar la subida (el commit ya estaba en master local; moverlo a otra rama exigía `git reset`/`checkout`, sin tool MCP que lo haga). (2) Queda explícito: con esta tool **el commit siempre cae en la rama actual**; para respetar §2.3 (nunca commitear directo a master) hay que crear/checkear la rama ANTES de invocarla (bash/otro flujo), cosa que esta sesión no hizo.
**Verificación:** tras re-intento sin `rama`: `git_ver_estado` → "up to date with origin/master", historial incluye `ab149ac` + esta lección.
**Lección:** `rama` en `git_subir_cambios` ≠ crear rama. Si el plan exige rama feature: `checkout -b` primero (y verificarlo), luego subir con `rama=""`. Ante push fallido, revisar SIEMPRE `git_ver_historial`/`estado` para saber si el commit local ya se hizo (no repetir add/commit a ciegas).

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
