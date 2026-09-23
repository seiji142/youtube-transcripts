# Lecciones aprendidas

Registro de errores reales y su resolución, para no repetirlos.

---

## 2026-09-23 — Regex monolítica rompió la collection de tests

**Archivo:** `services/youtube_subtitles.py`
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
