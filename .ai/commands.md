# Comandos del Proyecto

## Desarrollo

| Comando | Descripcion |
|---------|-------------|
| `pip install -r requirements.txt` | Instalar dependencias |
| `pytest tests/ -v` | Ejecutar tests (usar `brain-ai_run_tests`) |
| `winget install Gyan.FFmpeg` | Instalar FFmpeg en Windows |

## Git

| Comando | Descripcion |
|---------|-------------|
| `git status` | Ver estado del repositorio |
| `git add .` | Agregar todos los cambios |
| `git commit -m "msg"` | Commit con mensaje |
| `git push` | Subir cambios a origin |

## Clasificacion del cambio: SDD u ODD

Todo cambio autorizado se clasifica ANTES de escribir codigo. O lleva spec
(`docs/specs/<tema>.md`) o va en modo ODD. No hay tercera via.

### Prueba de reanudacion (decide; el tamano no)

Modo ODD solo si se cumplen las tres:
1. **Entendido**: no queda ninguna decision de producto abierta.
2. **Riesgo contenido**: no toca ningun escalador duro.
3. **Reanudable**: enumera las decisiones abiertas. Si alguna no se resuelve
   con el pedido o con `git diff` (incluida cualquier convencion que tengas
   que suponer), entonces no es ODD.

Falla cualquiera -> modo SDD (spec completo, y FICHA si hay entregable).

El conteo de archivos, lineas, tests o tareas NUNCA decide: un cambio de
una linea en auth es SDD; uno de 20 en un README puede ser ODD.

### Escaladores duros (siempre SDD)

Seguridad/auth, datos o migraciones, contratos de API que otros consumen,
dependencias nuevas, CI/workflows, crypto, permisos de `opencode.json`,
reglas y roles (`.ai/system.md`, `.ai/rules.md`, `.ai/commands.md`,
`.ai/agents.md`) o skills (`.agents/skills/`), operaciones irreversibles,
y `scripts/`.

### Que entrega cada modo

| | SDD | ODD |
|---|---|---|
| Documento | spec + FICHA | ninguno |
| Evidencia | §6, §7 y §8 del spec | commit + resultado observado en el chat |
| Verificacion pre-PR | obligatoria | obligatoria (identica) |
| Auditoria, si el proyecto la define | segun sus disparadores | segun sus disparadores |

En ODD la evidencia vive en el commit: asunto en imperativo y en el cuerpo
`ODD: <por que> / <que se observo>`. Sin esa linea no es ODD: es un cambio
sin evidencia.

### Prohibido

- Usar ODD para saltarse el criterio de aceptacion explicito del usuario.
- Declarar ODD despues de implementar para justificar la falta de spec.
- Partir un cambio SDD en varios ODD para esquivar el spec.

## Validacion pre-PR (obligatoria, bloqueante)

No hay sitio de dev (Pages = 1 sitio por repo; decision Q1). NINGUN PR se
abre sin completar la checklist de su variante, sin excepciones por
"cambio chico". Este es codigo no visual → **Variante B**.

### Variante B — codigo no visual

1. [ ] Tests en verde en local: `.venv\Scripts\python -m pytest tests/ -m "not integration" -q`
2. [ ] Lint: `.venv\Scripts\ruff check .` en verde (config en
   `pyproject.toml`; `ruff format` NO adoptado — reformatearía 38
   archivos, fuera de alcance).
3. [ ] Smoke test: `mcp_server` importa y registra las tools
   (tests `TestRegistroTools` en verde, incluidos en el paso 1).
4. [ ] Criterio de aceptacion EXPLICITO del usuario en el chat
   (ej: "search devuelve chunks citados"). Sin ese mensaje, NO hay PR.
   Cuenta: una frase sobre el CAMBIO ("el endpoint devuelve 200", "el
   typo ya no esta", "el kit quedo integrado").
   No cuenta: la orden de publicar ("abre el PR", "mergea", "subilo"):
   autoriza la accion, no acepta el resultado.

### Cierre

5. [ ] Abrir el PR via `scripts/gh-publish.ps1` (SIN `-Merge` todavia).
6. [ ] CI en verde en el PR (obligatorio; `main` lo exige por proteccion
   una vez activado el check `build` en la UI).
7. [ ] Recien entonces: merge via script (`-Merge`) -> verificar merge.

Regla: el riesgo percibido NUNCA saltea pasos. Lo que no tiene evidencia
(segun su variante + CI verde) se considera NO verificado.

## Publicacion (PRs y merges)

OBLIGATORIO: NUNCA usar `gh pr create` / `gh pr merge` directos.
Todo PR y merge pasa por `scripts/gh-publish.ps1` (desde la raiz del repo).

| Tarea | Comando |
|-------|---------|
| PR + merge `feature/x` -> `develop` | `.\scripts\gh-publish.ps1 -Rama feature/x -Base develop -Merge` |
| PR + merge `develop` -> `main` | `.\scripts\gh-publish.ps1 -Merge` |
| Solo crear PR (sin mergear) | Mismo comando sin `-Merge` |

## Memoria (project="youtube-transcripts")

| Comando | Descripcion |
|---------|-------------|
| `brain-ai_memory_search` | Buscar en memoria persistente |
| `brain-ai_memory_save` | Guardar episodio en memoria |
| `brain-ai_memory_consolidate` | Consolidar episodios en conocimiento |

## Uso

Los comandos de tests/build se ejecutan con `brain-ai_run_tests` / `brain-ai_run_command`
(no usar `brain-ai_run_tests` para builds). Fuente del flujo git/PR:
`seiji142/gitflow-scaffold` (template 2026.09.25).
