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
| `git push` | Subir cambios al remote |

## Memoria (project="youtube-transcripts")

| Comando | Descripcion |
|---------|-------------|
| `brain-ai_memory_search` | Buscar en memoria persistente |
| `brain-ai_memory_save` | Guardar episodio en memoria |
| `brain-ai_memory_consolidate` | Consolidar episodios en conocimiento |

## Uso

Los comandos de tests/build se ejecutan con `run_tests` / `run_command`
(no usar `run_tests` para builds).
