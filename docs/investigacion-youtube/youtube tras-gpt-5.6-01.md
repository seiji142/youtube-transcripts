## Conclusión ejecutiva

La mejor solución para brain-ai-01 no es depender de un único extractor, sino implementar un pipeline escalonado:

1. Intentar captions existentes con youtube-transcript-api.  
2. Intentar subtítulos mediante yt-dlp como segunda ruta de extracción.  
3. Si no hay captions, descargar únicamente el audio y transcribir localmente con faster-whisper.  
4. Opcionalmente, usar un proveedor externo de ASR como último fallback.  
5. Cachear la transcripción, dividirla en fragmentos con timestamps e indexarla para RAG.

Esto funciona en Windows, se integra bien con Python/FastAPI/MCP, admite español e inglés y puede operar sin infraestructura externa de pago.

---

# 1\. Correcciones importantes a la investigación inicial

## youtube-transcript-api no usa una API oficial

Aunque el nombre puede inducir a error, youtube-transcript-api:

* No usa la YouTube Data API oficial.  
* No requiere API key.  
* Consume endpoints internos de YouTube/InnerTube y analiza la respuesta.  
* Puede romperse cuando YouTube cambia esos endpoints.  
* Puede sufrir bloqueos de IP, especialmente desde proveedores cloud.

Por tanto, es una excelente primera opción, pero no debe considerarse una integración oficial o completamente estable.

## La API oficial de YouTube no resuelve el problema

La API oficial permite listar y descargar captions principalmente cuando el usuario autenticado tiene permisos sobre el video. No es una API general para descargar las captions de cualquier video público.

captions.download no sustituye a youtube-transcript-api para este caso.

Referencia:

* https://developers.google.com/youtube/v3/docs/captions/download

## u-transkript no es un fallback real para videos sin captions

Si u-transkript depende de InnerTube, sigue dependiendo de que exista una pista de subtítulos. Puede añadir traducción o procesamiento posterior, pero no genera una transcripción desde el audio por sí solo.

Por tanto:

* Captions disponibles → puede servir.  
* Sin captions → necesita un motor ASR adicional.

## yt-dlp \+ Whisper no necesita una API key de OpenAI

Hay dos implementaciones distintas:

* yt-dlp \+ OpenAI Transcription API: requiere API key y tiene coste.  
* yt-dlp \+ Whisper local: no necesita API key ni coste por minuto.

Para el segundo caso pueden utilizarse:

* faster-whisper  
* whisper.cpp  
* Whisper original de OpenAI

La opción más práctica para vuestro stack Python es normalmente faster-whisper.

## Las cifras de coste no deben fijarse en código o documentación

Los precios de OpenAI y de servicios como YouTubeTranscript.dev pueden cambiar. Conviene tratarlos como configuración y consultar las tarifas actuales antes de seleccionar un proveedor.

## Sobre NotebookLM

Es razonable inferir que NotebookLM aprovecha captions cuando están disponibles, pero su implementación interna no es un contrato público estable. Google puede cambiar el pipeline o añadir ASR propio. No recomendaría diseñar el sistema sobre la premisa de que conocemos exactamente su arquitectura interna.

---

# 2\. Evaluación de opciones

| Opción | Windows | MCP/Python | Sin captions | ES/EN | Dependencia externa | Evaluación |
| ----- | ----: | ----: | ----: | ----: | ----: | ----- |
| youtube-transcript-api | Sí | Excelente | No | Sí | YouTube no oficial | Mejor primera ruta |
| yt-dlp para subtítulos | Sí | Excelente | No | Sí | YouTube no oficial | Segundo extractor |
| yt-dlp \+ faster-whisper | Sí | Excelente | Sí | Sí | No, salvo YouTube | Fallback recomendado |
| yt-dlp \+ whisper.cpp | Sí | Buena | Sí | Sí | No | Buena alternativa CPU |
| OpenAI/Deepgram/AssemblyAI ASR | Sí | Excelente | Sí | Sí | Sí, de pago | Fallback opcional |
| YouTubeTranscript.dev/Supadata | Sí, REST | Excelente | Según plan | Sí | Sí, de pago | Reduce mantenimiento |
| Gemini con video/URL | Sí, API | Buena | Potencialmente | Sí | Google, de pago | Complemento, no base |
| API oficial de captions | Sí | Buena | No | Sí | Google OAuth | No sirve para videos públicos arbitrarios |
| notebooklm-client / cookies | Sí | Posible | Incierto | Sí | Backend privado Google | No recomendable en producción |
| Automatización de navegador | Sí | Mala | Incierto | Sí | Google/YouTube | Frágil y costosa de mantener |

---

# 3\. Opciones recomendadas

## A. youtube-transcript-api

### Ventajas

* Muy rápido cuando existen captions.  
* No descarga el video.  
* Devuelve segmentos con texto, inicio y duración.  
* Permite seleccionar idioma.  
* Maneja captions manuales y automáticas cuando YouTube las expone.  
* Integración Python directa.

### Limitaciones

* Usa interfaces no oficiales.  
* Puede recibir errores como:  
  * Video no disponible.  
  * Captions deshabilitadas.  
  * IP bloqueada.  
  * Consentimiento o restricción regional.  
  * Rate limiting.  
* Los servidores cloud sufren más bloqueos que conexiones residenciales.  
* Videos privados, restringidos por edad o región requieren tratamiento especial.

### Veredicto

Debe ser el primer intento, pero nunca la única estrategia.

Repositorio:

* https://github.com/jdepoix/youtube-transcript-api

---

## B. yt-dlp como segundo extractor de subtítulos

yt-dlp puede:

* Listar subtítulos manuales y automáticos.  
* Descargar VTT/SRT sin descargar el video completo.  
* Descargar únicamente audio si se necesita ASR.  
* Extraer metadatos: título, duración, canal, idiomas disponibles.

### Ventajas

* Proyecto muy mantenido.  
* Soporta gran cantidad de variantes de YouTube.  
* Es una pieza útil tanto para captions como para ASR.

### Limitaciones

* También depende de endpoints y comportamiento no oficial de YouTube.  
* YouTube cambia periódicamente firmas, tokens de reproductor y requisitos de cliente.  
* Hay que mantenerlo actualizado.  
* En algunos casos necesita cookies, PO tokens o configuración adicional.  
* Ejecutarlo como subprocess requiere controles de seguridad.

### Veredicto

Debe ser el segundo extractor y el encargado de descargar audio para el fallback ASR.

Repositorio:

* https://github.com/yt-dlp/yt-dlp

---

## C. faster-whisper local

Es la opción más equilibrada para generar una transcripción cuando no existen captions.

### Ventajas

* No necesita API key.  
* Procesamiento completamente local.  
* Modelos multilingües con buen soporte de español e inglés.  
* Mejor rendimiento y consumo de memoria que el Whisper Python original.  
* Puede ejecutarse en CPU con cuantización int8.  
* Aprovecha GPU NVIDIA cuando está disponible.

### Inconvenientes

* Un video largo puede tardar varios minutos en CPU.  
* Requiere descargar el audio.  
* Los modelos grandes consumen memoria y almacenamiento.  
* Los timestamps no siempre son tan precisos como los captions originales.  
* Nombres propios y audio de mala calidad pueden producir errores.

### Modelo sugerido

* Desarrollo/MVP CPU: small o medium, compute\_type=int8.  
* Producción con buena GPU: large-v3.  
* Si la velocidad importa más que la precisión, usar un modelo menor.  
* No usar modelos \*.en si se necesita español.

Repositorio:

* https://github.com/SYSTRAN/faster-whisper

### Alternativa: whisper.cpp

Adecuada si se busca:

* Distribución sencilla.  
* Ejecución eficiente en CPU.  
* Menos dependencias Python/CUDA.  
* Binarios controlados y modelos cuantizados.

Repositorio:

* https://github.com/ggerganov/whisper.cpp

Para brain-ai-01, empezaría con faster-whisper; usaría whisper.cpp si la instalación de CTranslate2/CUDA resulta problemática.

---

## D. ASR externo opcional

Proveedores posibles:

* OpenAI Transcription API.  
* Deepgram.  
* AssemblyAI.  
* Google Cloud Speech-to-Text.  
* Azure Speech.  
* Servicios especializados en transcripciones de YouTube.

### Cuándo tiene sentido

* El servidor no tiene capacidad de CPU/GPU suficiente.  
* Se necesita menor latencia.  
* Se quiere reducir mantenimiento.  
* La precisión o diarización del proveedor es importante.

### Problemas

* Coste recurrente.  
* Privacidad y transferencia del audio.  
* Límites de tamaño/duración.  
* Dependencia de un proveedor.  
* El proveedor de ASR no elimina necesariamente el problema de descargar el audio desde YouTube.

Recomendaría implementarlo como adaptador opcional, no como dependencia obligatoria.

---

## E. Gemini directamente sobre un video

Algunos modelos y APIs de Google ofrecen comprensión de video, archivos subidos o tratamiento de ciertos enlaces. Sin embargo:

* La disponibilidad depende del modelo, región y versión de API.  
* Los límites para URLs de YouTube pueden cambiar.  
* Puede no devolver una transcripción completa y reutilizable.  
* Es más difícil controlar timestamps, caché, chunking y citas.  
* No conviene asumir que replica contractualmente a NotebookLM.

Puede ser útil para análisis multimodal —diapositivas, imágenes, acciones—, pero no lo usaría como base del sistema de transcripción.

---

## F. Clientes no oficiales de NotebookLM

notebooklm-client, servidores MCP basados en cookies y automatización de NotebookLM pueden funcionar, pero presentan riesgos importantes:

* Cookies de sesión y expiración.  
* Posibles verificaciones de cuenta.  
* APIs privadas sin estabilidad.  
* Cambios de frontend.  
* Riesgo de bloqueo de cuenta.  
* Dificultad para operar de manera desatendida.

Son apropiados para experimentación personal, no para una integración central de producción.

---

# 4\. Arquitectura propuesta

## Flujo principal

text

MCP tool  
   │  
   ▼  
Validación y normalización de URL  
   │  
   ▼  
Consulta de caché  
   │  
   ├── Encontrado → devolver transcript/resource  
   │  
   ▼  
Extracción de metadatos  
   │  
   ▼  
1\. youtube-transcript-api  
   │  
   ├── Éxito → normalizar y guardar  
   │  
   ▼  
2\. yt-dlp: subtítulos manuales/automáticos  
   │  
   ├── Éxito → convertir VTT y guardar  
   │  
   ▼  
3\. yt-dlp: descargar solo audio  
   │  
   ▼  
faster-whisper local  
   │  
   ├── Error/capacidad insuficiente  
   │   ▼  
   │   4\. Proveedor ASR externo opcional  
   │  
   ▼  
Normalización \+ timestamps \+ chunking  
   │  
   ▼  
Índice RAG y respuesta MCP

## Preferencia de pistas

Sugiero este orden:

1. Captions manuales en el idioma solicitado.  
2. Captions manuales en idioma original.  
3. Captions automáticas en idioma solicitado.  
4. Captions automáticas en idioma original.  
5. Traducción de una pista existente.  
6. ASR sobre audio.

Debe conservarse siempre:

* Idioma original.  
* Tipo de fuente.  
* Si es manual o automática.  
* Si fue traducida.  
* Motor usado.  
* Fecha de extracción.

---

# 5\. Diseño de tools MCP

No conviene que una única llamada MCP permanezca abierta durante diez minutos transcribiendo un video. Recomiendo dos modalidades.

## Tool rápida/unificada

JSON

{  
  "name": "youtube\_transcript",  
  "arguments": {  
    "url": "https://www.youtube.com/watch?v=...",  
    "languages": \["es", "en"\],  
    "allow\_asr": true,  
    "translate\_to": null,  
    "include\_timestamps": true,  
    "max\_duration\_seconds": 7200  
  }  
}

Respuesta rápida si existen captions:

JSON

{  
  "status": "completed",  
  "video\_id": "...",  
  "title": "...",  
  "language": "es",  
  "source": "youtube\_manual\_captions",  
  "duration\_seconds": 1432,  
  "transcript\_id": "...",  
  "text": "...",  
  "segments": \[  
    {  
      "start": 12.4,  
      "end": 16.8,  
      "text": "..."  
    }  
  \]

}

Si necesita ASR y supera el timeout:

JSON

{  
  "status": "processing",  
  "job\_id": "...",  
  "estimated\_strategy": "local\_faster\_whisper"

}

## Tool de estado

JSON

{  
  "name": "youtube\_transcript\_status",  
  "arguments": {  
    "job\_id": "..."  
  }  
}

## Tool de lectura paginada

Para videos largos, no debe devolverse toda la transcripción dentro de una única respuesta MCP.

JSON

{  
  "name": "youtube\_transcript\_read",  
  "arguments": {  
    "transcript\_id": "...",  
    "start\_seconds": 600,  
    "end\_seconds": 900,  
    "max\_chars": 20000  
  }

}

## Tool de búsqueda RAG

JSON

{  
  "name": "youtube\_transcript\_search",  
  "arguments": {  
    "transcript\_id": "...",  
    "query": "¿Qué dijo sobre los límites de la API?",  
    "top\_k": 8  
  }  
}

Esta última herramienta es la que realmente acerca el sistema a NotebookLM: no solo obtiene texto, sino que recupera los fragmentos relevantes y conserva citas temporales.

---

# 6\. Almacenamiento e indexación

## MVP sin infraestructura adicional

* SQLite para:  
  * Videos.  
  * Jobs.  
  * Metadatos.  
  * Segmentos.  
  * Estado de errores.  
* Ficheros locales para:  
  * JSON de transcripción.  
  * Audio temporal.  
* SQLite FTS5 para búsqueda textual.

Esto funciona bien en un único servidor Windows y no requiere Redis, PostgreSQL ni servicios externos.

## Evolución posterior

Si necesitáis búsqueda semántica:

* Chroma o Qdrant local.  
* FAISS dentro del proceso.  
* PostgreSQL \+ pgvector si ya existe infraestructura.

Cada chunk debería incluir:

JSON

{  
  "video\_id": "...",  
  "start": 620.2,  
  "end": 684.7,  
  "text": "...",  
  "language": "es",  
  "source": "faster\_whisper",  
  "chunk\_index": 17

}

El asistente debería citar respuestas con enlaces temporales:

text

https://www.youtube.com/watch?v=VIDEO\_ID\&t=620s

## Chunking recomendado

* 500–1.000 tokens por fragmento.  
* Solapamiento de 10–15%.  
* No cortar frases si es posible.  
* Mantener el timestamp inicial y final.  
* Para captions muy fragmentadas, unir segmentos antes del chunking.

---

# 7\. Implementación en Windows

## Componentes

* Python compatible con el proyecto.  
* youtube-transcript-api.  
* yt-dlp.  
* faster-whisper.  
* FFmpeg disponible en PATH.  
* SQLite.  
* Worker separado o cola local.

FFmpeg puede instalarse mediante:

* winget  
* Chocolatey  
* Un binario versionado junto al servicio

Si se distribuye FFmpeg con el producto, hay que revisar las implicaciones LGPL/GPL de la build seleccionada.

## Ejecución de trabajos

No usaría FastAPI BackgroundTasks como única cola para trabajos largos, porque:

* No es durable.  
* Los trabajos se pierden al reiniciar.  
* Puede saturar el proceso web.

Para una sola máquina puede implementarse:

* Tabla de jobs en SQLite.  
* Un proceso worker dedicado.  
* Concurrencia máxima configurable.  
* Heartbeat y recuperación de jobs interrumpidos.

Ejemplo:

text

FastAPI/MCP process  
    │  
    ├── crea job en SQLite  
    │  
    └── devuelve job\_id

Worker process  
    │  
    ├── reclama job  
    ├── descarga/transcribe

    └── actualiza estado

En Windows puede ejecutarse como servicio mediante NSSM, Task Scheduler o el mecanismo de despliegue que ya utilice brain-ai-01.

---

# 8\. Manejo de idiomas

## Captions

* Solicitar primero es, después en, o viceversa según la petición.  
* Diferenciar es, es-419, en, en-US, etc.  
* Si solo existe una pista traducible, decidir explícitamente si se acepta traducción automática.

## ASR

faster-whisper puede:

* Detectar el idioma.  
* Recibir un idioma explícito.  
* Transcribir español e inglés.  
* Manejar cierto cambio de idioma, aunque no siempre perfectamente.

Recomendación:

* Permitir language="auto".  
* Permitir al usuario forzar es o en.  
* Para videos cortos o con introducciones musicales, usar metadata/captions como pista de idioma.  
* Guardar la probabilidad o confianza de detección cuando esté disponible.

Whisper puede traducir audio a inglés, pero no debe tratarse como un traductor general hacia cualquier idioma. Para traducción a español, utilizar un paso posterior con el LLM.

---

# 9\. Riesgos principales

## 9.1 Bloqueo y rate limiting de YouTube

Es el riesgo operativo más importante.

Síntomas:

* HTTP 429\.  
* RequestBlocked.  
* “Video unavailable” falso.  
* Endpoints de captions vacíos.  
* Descargas que funcionan localmente pero no en el servidor cloud.

Mitigaciones:

* Cachear por video\_id \+ idioma \+ tipo de pista.  
* No repetir extracciones innecesarias.  
* Limitar concurrencia.  
* Aplicar backoff exponencial y jitter.  
* Mantener yt-dlp actualizado.  
* Implementar circuit breaker tras varios 429\.  
* No consultar repetidamente variantes de idioma si ya se conoce el inventario.  
* Registrar diferencias entre “sin captions” y “acceso bloqueado”.

No recomendaría convertir proxies residenciales en parte obligatoria de la arquitectura. Añaden coste, implicaciones legales y riesgo reputacional. Si se necesitan, deben ser una decisión operativa explícita.

## 9.2 Cambios de YouTube

Tanto youtube-transcript-api como yt-dlp son dependencias de mantenimiento continuo.

Mitigación:

* Aislar cada extractor detrás de una interfaz.  
* Poder habilitar/deshabilitar providers mediante configuración.  
* Fijar versiones, pero actualizar periódicamente.  
* Tener tests de integración con un conjunto de videos públicos.  
* Separar errores de extracción, captions y ASR.

Interfaz sugerida:

Python

class TranscriptProvider:  
    async def can\_handle(self, request) \-\> bool: ...

    async def fetch(self, request) \-\> TranscriptResult: ...

Providers:

text

YouTubeTranscriptApiProvider  
YtDlpSubtitleProvider  
FasterWhisperProvider

ExternalAsrProvider

## 9.3 Duración, almacenamiento y abuso

Un usuario podría enviar un video de diez horas o una playlist completa.

Controles necesarios:

* Duración máxima configurable.  
* Tamaño máximo de audio.  
* Número máximo de jobs concurrentes.  
* Timeout de descarga.  
* Cuota por usuario.  
* Rechazar playlists inicialmente.  
* Borrar audio tras completar el ASR.  
* Límite de espacio total y política LRU.

## 9.4 Seguridad

* Aceptar únicamente hosts de YouTube permitidos:  
  * youtube.com  
  * www.youtube.com  
  * m.youtube.com  
  * youtu.be  
  * youtube-nocookie.com, si se decide soportarlo  
* Extraer y validar el ID del video.  
* No pasar la URL a subprocess usando shell=True.  
* Usar subprocess\_exec o argumentos separados.  
* No permitir flags arbitrarios para yt-dlp.  
* Utilizar directorios temporales aislados.  
* Evitar que el usuario determine paths de salida.  
* Limitar redirects y validar el destino final.

## 9.5 Cookies y autenticación

Cookies pueden ser necesarias para:

* Videos privados.  
* Restricción por edad.  
* Contenido regional.  
* Contenido que exige sesión.

Pero almacenarlas en el servidor implica:

* Secretos de cuenta.  
* Caducidad.  
* Riesgo de bloqueo.  
* Posibles verificaciones interactivas.

Recomendación para la primera versión: soportar solamente videos públicos sin autenticación.

## 9.6 Términos de servicio y copyright

La descarga y procesamiento de audio puede estar limitada por:

* Términos de YouTube.  
* Copyright.  
* Jurisdicción.  
* Uso comercial o redistribución.

Medidas prudentes:

* Procesar únicamente a petición del usuario.  
* No redistribuir audio/video.  
* Conservar solo la transcripción cuando sea necesario.  
* Borrar el audio temporal.  
* Documentar que el usuario debe tener derecho a procesar el contenido.  
* Revisar los términos con asesoría legal si se ofrece como servicio público.

## 9.7 Calidad de ASR

Problemas esperables:

* Música o ruido.  
* Varios hablantes.  
* Acentos.  
* Código, acrónimos y nombres propios.  
* Solapamiento de voces.  
* Audio bilingüe.  
* Timestamps aproximados.

Mitigaciones:

* Preferir captions manuales sobre ASR.  
* Permitir vocabulario/contexto inicial.  
* Mantener el texto original antes de “corregirlo” con un LLM.  
* No permitir que el LLM invente palabras durante limpieza.  
* Etiquetar la procedencia y nivel de confianza.

---

# 10\. Plan de implementación recomendado

## Fase 1: MVP

Implementar:

1. Parser seguro de URLs.  
2. youtube-transcript-api.  
3. Selección español/inglés.  
4. Segmentos con timestamps.  
5. Caché SQLite.  
6. Tool youtube\_transcript.  
7. Límites de duración y tamaño.  
8. Métricas y errores estructurados.

Esto cubre rápidamente la mayoría de videos con captions.

## Fase 2: Fallback real

Añadir:

1. yt-dlp para inspeccionar y descargar subtítulos.  
2. Descarga bestaudio.  
3. FFmpeg.  
4. faster-whisper.  
5. Jobs asíncronos.  
6. Tool youtube\_transcript\_status.  
7. Limpieza automática de temporales.

## Fase 3: Experiencia NotebookLM/RAG

Añadir:

1. Chunking semántico.  
2. SQLite FTS5 o vector store local.  
3. youtube\_transcript\_search.  
4. Citas con timestamps.  
5. Resúmenes jerárquicos para videos largos.  
6. Preguntas y respuestas limitadas a evidencia recuperada.

## Fase 4: Resiliencia

Añadir:

1. Proveedor ASR externo opcional.  
2. Circuit breaker.  
3. Métricas por proveedor.  
4. Tests de integración periódicos.  
5. Reintentos con backoff.  
6. Panel o endpoint de salud.  
7. Políticas de retención y cuotas.

---

# Recomendación final

La arquitectura que adoptaría es:

text

youtube-transcript-api  
        ↓ fallback  
yt-dlp subtitles  
        ↓ fallback  
yt-dlp audio \+ faster-whisper local  
        ↓ fallback opcional

ASR externo

Con:

* SQLite como caché y cola inicial.  
* Worker separado para ASR.  
* Timestamps preservados.  
* Tools MCP de creación, estado, lectura y búsqueda.  
* RAG sobre chunks, no envío indiscriminado de toda la transcripción al modelo.  
* Videos públicos únicamente en la primera versión.  
* Sin dependencia de NotebookLM, cookies de Google ni automatización de navegador.

El cambio más importante respecto a la propuesta original es que u-transkript no soluciona la ausencia de captions. El fallback correcto debe ser ASR sobre el audio, y faster-whisper local es la opción con mejor equilibrio entre coste, control, soporte de Windows e integración Python.  
