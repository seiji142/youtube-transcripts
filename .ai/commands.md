# Comandos del Proyecto

## Desarrollo

| Comando | Descripcion |
|---------|-------------|
| `pip install -r requirements.txt` | Instalar dependencias |
| `pytest tests/ -v` | Ejecutar tests (usar `run_tests`) |
| `winget install Gyan.FFmpeg` | Instalar FFmpeg en Windows |

## Git

| Comando | Descripcion |
|---------|-------------|
| `git status` | Ver estado del repositorio |
| `git add .` | Agregar todos los cambios |
| `git commit -m "msg"` | Commit con mensaje |
| `git push` | Subir cambios a origin |

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

Los comandos de tests/build se ejecutan con `run_tests` / `run_command`
(no usar `run_tests` para builds). Fuente del flujo git/PR:
`seiji142/gitflow-scaffold` (template 2026.09.25).
