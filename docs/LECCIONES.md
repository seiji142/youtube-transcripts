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
