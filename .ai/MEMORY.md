# Memoria Persistente - Instrucciones de Uso

## Servidor
- **Endpoint:** http://localhost:8000
- **Proyecto:** youtube-transcripts
- **Cliente:** brain-ai-01/clients/memoria.py
- **MCP Bridge:** brain-ai-01/mcp_bridge.py
- **Estado:** Activo (verificar con GET /health)

## Herramientas MCP Disponibles

### brain-ai_memory_search
Busca episodios y conocimiento en la memoria persistente.
**Usar ANTES de responder preguntas sobre decisiones pasadas.**

Parámetros:
- `query` (requerido): Texto a buscar
- `project`: Proyecto a filtrar (default: "youtube-transcripts")
- `top_k`: Número de resultados (default: 5)
- `collection`: "semantic" (conocimiento consolidado) o "episodic" (eventos crudos)

### brain-ai_memory_save
Guarda un episodio en la memoria persistente.
**Usar DESPUÉS de tomar una decisión importante.**

Parámetros:
- `project` (requerido): Nombre del proyecto (usar "youtube-transcripts")
- `decision` (requerido): Decisión tomada o lección aprendida
- `evidence`: Evidencia que respalda la decisión
- `tags`: Tags descriptivos

### brain-ai_memory_consolidate
Consolida episodios en conocimiento semántico.
**Ejecutar periódicamente para promover episodios repetidos.**

Parámetros:
- `project`: Proyecto a consolidar (usar "youtube-transcripts")

## Cuándo guardar en memoria (AUTO)
DESPUÉS de cada sesión exitosa, DEBES usar `brain-ai_memory_save` con
`project="youtube-transcripts"`:
1. **Decisiones de código:** por qué se eligió X sobre Y
2. **Patrones de error:** qué falló y cómo se resolvió
3. **Preferencias del usuario:** qué le gusta, qué rechaza
4. **Configuraciones efectivas:** qué configuración funcionó
5. **Lecciones aprendidas:** qué haría diferente

## Cuándo buscar en memoria (ANTES de responder)
ANTES de generar código o tomar decisiones:
1. Usar `brain-ai_memory_search(query="...", project="youtube-transcripts")`
2. Si hay resultados, usar esa información para responder
3. Si no hay resultados, responder con incertidumbre ("no tengo información previa")

## Categorías de memoria
- **decisión:** por qué se eligió una tecnología, patrón o aproximación
- **error:** qué falló, por qué falló, cómo se resolvió
- **configuración:** qué configuración funcionó (modelos, reglas, versiones)
- **preferencia:** qué le gusta al usuario (idioma, estilo, formato)
- **lección:** qué haría diferente la próxima vez

## Ejecución de tests y comandos

| Situación | Herramienta | Ejemplo |
|-----------|-------------|---------|
| Ejecutar solo tests | `brain-ai_run_tests` + `brain-ai_test_status` | `pytest tests/ -m "not integration" -q` |
| Verificar build / comandos consola | `brain-ai_run_command` + `brain-ai_command_status` | scripts de verificación, `pip install` (NO usar `run_tests` para esto) |

## Retrieval
- Usar `brain-ai_memory_search(query, project="youtube-transcripts")`
- Combina búsqueda episódica + semántica

## Consolidación
- Ejecutar `brain-ai_memory_consolidate(project="youtube-transcripts")` periódicamente
- Promueve episodios a semántico si confidence >= 0.6
