---
titulo: Regla de clasificacion de cambios (escaladores y modo con evidencia)
estado: implementado
entradas:
  - Regla ya vigente en gentle-ai, personalizar-comportamiento-01, gitflow-scaffold, banco-diseno, flujo-ai-lab, piloto-nuevo y sitio-viajes
salidas:
  - .ai/commands.md con la seccion de clasificacion
  - opencode.json que carga .ai/commands.md
dependencias:
  - .ai/commands.md
  - opencode.json
tablas_impactadas: []
criterio_aceptacion: Al pedir un cambio que toca un escalador duro el agente exige spec antes de escribir, y un cambio chico se ejecuta sin documento.
---

# Regla de clasificacion de cambios

## 1. Problema

Este repo tiene gate pre-PR (Variante B) y seccion de publicacion, pero **no
clasifica el cambio**: nada decide si hace falta spec. Ademas `.ai/commands.md`
**no esta en `instructions`** de `opencode.json`, asi que una seccion escrita
ahi nunca se cargaria. El gate pide "criterio de aceptacion EXPLICITO" sin
definir que cuenta: "abre el PR" es una orden, no un criterio.

## 2. Alcance

- Incluye: seccion de clasificacion en `.ai/commands.md`, la aclaracion de que
  cuenta como criterio en el punto 4 de la Variante B, y la entrada en
  `instructions`.
- Excluye (explicito): la migracion de esquema de `opencode.json` que estaba
  sin commitear (`provider` -> `providers`, `options` -> `body`, `permission` ->
  `permissions`, `mcp` -> `mcp.servers`). No se commitea aca ni se descarta.

## 3. Modulos / piezas

- `.ai/commands.md`: seccion nueva entre "Git" y "Validacion pre-PR"; 4 lineas
  en el punto 4 de la Variante B.
- `opencode.json`: `.ai/commands.md` en `instructions` (unica linea commiteada).

## 4. Stack y dependencias

Markdown + JSON; Python + pytest + ruff para el servidor MCP. **Este repo no
tiene `scripts/ci_checks.py` ni validador de specs**: la verificacion es
`json.tool` + revision manual del diff, mas la suite existente sin tocar.

## 5. Diseno

Se copia la seccion **literal** desde `gentle-ai` (extraida por script, no
retecleada) para que las 8 copias se puedan comparar por contenido. Alternativa
descartada: reescribirla con el vocabulario de este repo - cada copia divergente
se desincroniza en silencio.

Para `opencode.json` se stagea el blob de HEAD + la linea nueva
(`hash-object` + `update-index --cacheinfo`): el commit contiene solo lo pedido
y el trabajo del usuario sigue intacto en el working tree.

## 6. Plan de verificacion

- Que ejecuta `fx-test`: `python -m json.tool opencode.json` -> 0, y la suite
  existente (`.venv\Scripts\python -m pytest tests/ -m "not integration" -q`)
  sigue igual de verde: el cambio es markdown + una linea de JSON.
- Que revisa `my-review`: que la seccion sea identica a la de `gentle-ai`
  (comparacion de contenido), que el diff commiteado de `opencode.json` sea una
  sola linea, y que el working tree conserve la migracion sin commitear.

## 7. Criterio de aceptacion

Al pedir un cambio que toca un escalador duro el agente exige spec antes de
escribir, y un cambio chico se ejecuta sin documento.

## 8. Lecciones del fix (DESPUES de implementar, obligatorio)

- Fix aplicado [GENERAL]: el token `D2ED7B56DDEF894D` usado en los repos
  anteriores como sha de la seccion no era un hash de contenido: salio de
  `Get-Content`, que decodifica en ANSI y manglea los acentos. Aca se compara
  contenido, no hashes medidos por PowerShell.
- Que seccion de este spec cambia por el fix: la §6, que ahora compara
  contenido en vez de hashes externos.
- Test anti-regresion que lo cubre: el script de propagacion compara la seccion
  extraida contra la de `gentle-ai` y aborta si difiere.
