# Agentes

Punto de entrada para instrucciones del modelo IA.

## Archivos de configuración

Lee los siguientes archivos para entender el contexto del proyecto:

| Archivo | Propósito |
|---------|-----------|
| `.ai/system.md` | Rol, tono y postura epistémica del agente |
| `.ai/rules.md` | Reglas de seguridad y restricciones |
| `.ai/context.md` | Stack tecnológico y contexto del proyecto |
| `.ai/agents.md` | Definición de agentes especialistas |
| `.ai/commands.md` | Comandos personalizados/admin |
| `.ai/MEMORY.md` | Persistencia de contexto entre sesiones |

## Uso

Al iniciar una sesión, el modelo debe:
1. Leer este archivo (AGENTS.md)
2. Cargar los archivos `.ai/` correspondientes
3. Seguir las reglas y instrucciones definidas
