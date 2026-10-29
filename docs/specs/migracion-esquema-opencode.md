---
titulo: Migracion de opencode.json al esquema v2 (provider, options, permissions, mcp.servers)
estado: implementado
entradas:
  - opencode.json de youtube-transcripts con esquema v1 (provider.options, permission, mcp plano, enabled)
  - Medición de la config efectiva del v1 auto-migrado por OpenCode v2
  - Decision del humano: los tres permisos con efecto allow
salidas:
  - opencode.json migrado a v2 sin claves de compatibilidad
  - docs/specs/migracion-esquema-opencode.md (este documento)
  - docs/LECCIONES.md con los incidentes de la sesion
dependencias:
  - opencode.json
  - https://opencode.ai/config.json (schema v2)
  - .venv del repo (pytest 9.1.1, ruff 0.16.9)
  - .github/workflows/ci.yml (gate externo: pytest sin red)
tablas_impactadas: []
criterio_aceptacion: La config efectiva del archivo migrado es equivalente a la del v1 auto-migrado salvo los cambios declarados (settings en vez de options, efecto de permisos a allow y la regla edit duplicada que desaparece), con 335 tests en verde y ruff limpio.
---

# Migracion de opencode.json al esquema v2

## 1. Problema

`opencode.json` esta en el esquema v1: `provider.options`, `permission` como
objeto y `mcp.<nombre>` plano con `enabled: true`.

OpenCode v2 **no rechaza** el archivo v1, lo migra en runtime. El defecto no
es una falla: es que este repo ensena el esquema viejo y depende de una capa
de compatibilidad. Medido en los repos hermanos y aca:

- La migracion automatica convierte `permission.write` a `edit` y lo suma al
  `edit` explicito: deja **la regla `edit` duplicada**.
- `provider` (singular) se descarta; la clave efectiva es `providers`.
- `mcp.<nombre>` + `enabled: true` pasa a `mcp.servers.<nombre>`; la ausencia
  de `enabled` significa habilitado.

## 2. Alcance

- Incluye: las claves de `opencode.json` de este repo y el efecto de los
  permisos (`ask` -> `allow`, decision del humano en el chat).
- Excluye (explicito): `model`; el contenido de `.ai/`, `services/`, `tests/`
  y `mcp_server.py`; las rutas y comandos de los tres servidores MCP, que se
  conservan byte a byte y solo cambian de nivel.
- Excluye: `compaction` y `skills`, **no existen** en este repo. No se
  agregan por copia de los hermanos.

## 3. Modulos / piezas

Un solo archivo de configuracion, `opencode.json`:

| v1 (antes) | v2 (despues) |
|---|---|
| `provider.<id>.models.<m>.options` | `providers.<id>.models.<m>.settings` |
| `permission` objeto (bash/webfetch/write/edit) | `permissions` array (shell/edit/webfetch) |
| `mcp.<nombre>` + `enabled: true` | `mcp.servers.<nombre>` sin `enabled` |

Ademas: `docs/specs/migracion-esquema-opencode.md` (este spec) y las entradas
de `docs/LECCIONES.md` que exige `rules.md` §10.

## 4. Stack y dependencias

Python 3.10+ con `.venv` propio (`pytest 9.1.1`, `ruff 0.16.9`). El CI corre
`python -m pytest tests/ -m "not integration" -q` en `ubuntu-latest`; el
lint es local (`ruff check .`), no esta en el workflow. Sin build estatico.

## 5. Diseno

Traduccion clave por clave segun `https://opencode.ai/config.json`, validada
contra la config efectiva y no contra el nombre que sugiere el schema.

Decisiones:

- **`options` -> `settings`, no `body`**: medicion en directorios temporales
  con cuatro variantes. El v1 auto-migrado devuelve
  `{"settings": {"temperature": 0.7, "max_tokens": 4000}}`; la variante con
  `body` devuelve `{"body": {...}}`, que se fusiona en el request HTTP crudo.
  Misma forma, semantica distinta. Alternativa descartada: `body`, que era la
  suposicion del spec `regla-clasificacion-cambios.md` §2 y estaba sin
  verificar.
- **`permission.write` no se reescribe aparte**: v2 usa `edit` para escritura
  y edicion; la regla `edit` ya cubre ambas y evita el duplicado que produce
  la compatibilidad.
- **Efecto `allow` en las tres reglas**: decision del humano en el chat (v1
  tenia `bash: allow`, `webfetch: ask`, `write: ask`, `edit: ask`).
  Consecuencia declarada: shell, edicion y webfetch dejan de pedir
  confirmacion en este repo. Las reglas del global siguen vigentes porque los
  arrays de `permissions` se concatenan y las del global se agregan despues.
- **Los tres MCP se conservan**: `git_publisher`, `brain-ai` y
  `youtube-transcripts` son dominio de este repo; solo cambian de nivel.

## 6. Plan de verificacion

1. `python -m json.tool opencode.json` -> exit 0.
2. `.venv\Scripts\python -m pytest tests/ -m "not integration" -q` -> verde.
3. `.venv\Scripts\python -m ruff check .` -> `All checks passed!`.
4. `opencode debug config` en el worktree -> el documento del proyecto declara
   `providers.groq.models."openai/gpt-oss-20b".settings`, `permissions` con
   shell/edit/webfetch en `allow` y `mcp.servers` con los tres servidores.
5. Equivalencia contra el v1 auto-migrado (`git show HEAD:opencode.json` en un
   directorio temporal), comparando config efectiva normalizada: `model`,
   `model_settings`, `instructions`, `mcp_servers`, `mcp_commands` y
   `compaction` iguales; `permissions` sin reglas perdidas ni agregadas.
6. Smoke test cubierto por el paso 2 (`TestRegistroTools` esta en la suite,
   pero `mcp_server.py` no se modifica).

## 7. Criterio de aceptacion

La config efectiva del archivo migrado es equivalente a la del v1
auto-migrado salvo los cambios declarados (`settings` en vez de `options`,
efecto de permisos a `allow` y la regla `edit` duplicada que desaparece), con
335 tests en verde y ruff limpio.

## 8. Lecciones del fix (DESPUES de implementar, obligatorio)

- Fix aplicado [GENERAL]: el nombre de la clave destino no se deduce del
  schema, se mide sobre la config efectiva del v1 auto-migrado. `options` cae
  en `settings`; `body` es el request HTTP crudo y habria cambiado la
  semantica sin cambiar la forma.
- Fix aplicado [LOCAL]: el `opencode.json` pendiente traia `body`; se
  reemplazo por `settings` y la comparacion de §6 paso a incluir
  `model_settings`.
- Que seccion de este spec cambia por el fix: §2, §5 y §6, que ahora declaran
  `settings` como traduccion medida y el efecto `allow` como decision humana.
- Test anti-regresion que lo cubre: el paso 5 de §6 compara `model_settings`
  entre el archivo nuevo y el v1 auto-migrado; si vuelve a aparecer `body` o
  se pierde un servidor MCP, la comparacion deja de dar iguales.
- Los incidentes de shell de la sesion (BOM de PowerShell, `NativeCommandError`
  de `git checkout -b`) quedan registrados en `docs/LECCIONES.md` segun
  `rules.md` §10.
