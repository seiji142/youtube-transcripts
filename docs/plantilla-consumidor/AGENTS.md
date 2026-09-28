# Agentes

Punto de entrada para instrucciones del modelo IA del proyecto
**consumidor** de youtube-transcripts.

## Archivos de configuración

Lee los siguientes archivos para entender tu rol en este proyecto:

| Archivo | Propósito |
|---------|-----------|
| `.ai/system.md` | Rol (operador de videos), postura epistémica y reglas de fidelidad al video |
| `.ai/context.md` | Tools MCP disponibles, flujo de trabajo y gotchas |

## Uso

Al iniciar una sesión, el modelo debe:
1. Leer este archivo (AGENTS.md)
2. Cargar los archivos `.ai/` correspondientes
3. Seguir las reglas y instrucciones definidas (especialmente las
   reglas de fidelidad de `.ai/system.md` antes de redactar
   cualquier entregable basado en un video)

## Por qué existe

Sin una capa de comportamiento, los agentes usan las tools del MCP
`youtube-transcripts` con defaults del modelo: inventan datos que el
video no dice, no citan momentos y preguntan en vez de ejecutar
(evidencia: fase P3 de `youtube-transcripts/docs/PLAN_PUENTE_MULTIPROYECTO.md`).
Este scaffold previene esos fallos.
