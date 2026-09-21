Sí. La solución debe separar tres problemas diferentes:

1. Obtener subtítulos existentes.  
2. Transcribir el audio cuando no hay subtítulos.  
3. Analizar elementos visuales si también interesa lo que aparece en pantalla.

Después de revisar las alternativas disponibles y sus limitaciones, la solución completamente gratuita más viable es:

text

youtube-transcript-api  
        ↓ si falla  
yt-dlp: subtítulos manuales o automáticos  
        ↓ si no existen  
yt-dlp: descarga solo el audio  
        ↓  
faster-whisper local  
        ↓  
normalización, caché y búsqueda  
        ↓

OpenCode analiza la transcripción mediante MCP

No requiere OpenAI, Google Cloud, AssemblyAI ni ninguna API de pago. Todo se ejecuta en brain-ai-01.

*“100% gratis” significa sin APIs ni servicios de pago. Sigue existiendo el coste normal de máquina, almacenamiento, electricidad y conexión.*

---

# 1\. Resultado de la investigación

## 1.1 La API oficial de YouTube no sirve para este caso

YouTube Data API tiene endpoints de captions, pero no permite descargar libremente los subtítulos de cualquier video público. captions.download requiere OAuth y permisos suficientes sobre el video.

Por tanto, no puede ser la base de una herramienta que reciba videos arbitrarios.

Documentación:

* [YouTube captions.download](https://developers.google.com/youtube/v3/docs/captions/download)  
* [YouTube captions.list](https://developers.google.com/youtube/v3/docs/captions/list)

---

## 1.2 youtube-transcript-api

Es la opción más rápida para videos que ya tienen subtítulos manuales o automáticos.

### Ventajas

* Python.  
* Funciona en Windows.  
* No necesita API key.  
* Normalmente responde en pocos segundos.  
* Devuelve texto y timestamps.  
* Permite seleccionar español o inglés.  
* No descarga el audio o video.

### Limitaciones

* No usa la API oficial de YouTube.  
* Depende de endpoints internos de YouTube.  
* No funciona si el video no tiene captions.  
* Puede fallar por bloqueo de IP o HTTP 429\.  
* Los centros de datos y proveedores cloud suelen tener más bloqueos que una conexión residencial.  
* No es suficiente como única solución.

Repositorio:

* [jdepoix/youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api)

### Evaluación

Excelente primera opción, pero necesita fallback.

---

## 1.3 yt-dlp

yt-dlp es actualmente una de las herramientas gratuitas más completas para:

* Consultar metadatos.  
* Enumerar subtítulos.  
* Descargar subtítulos manuales.  
* Descargar subtítulos automáticos.  
* Descargar solamente el audio.  
* Trabajar con streams fragmentados de YouTube.

Repositorio:

* [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp)

### Ventajas

* Funciona en Windows.  
* Puede usarse desde Python o mediante CLI.  
* Proyecto activamente mantenido.  
* No necesita API key.  
* Permite descargar solo el audio, no el video entero.  
* Sirve como puente hacia Whisper.

### Limitaciones

* También usa mecanismos no oficiales de YouTube.  
* Debe mantenerse actualizado.  
* Puede sufrir bloqueos de IP.  
* Algunos videos pueden requerir cookies, sesión, tokens o un runtime JavaScript.  
* No conviene pasar argumentos enviados por el usuario directamente al proceso.

### Evaluación

Es el segundo extractor y el mecanismo recomendado para obtener audio cuando no hay captions.

---

## 1.4 Whisper original

Whisper puede ejecutarse localmente y es gratuito.

Repositorio:

* [openai/whisper](https://github.com/openai/whisper)

Sin embargo, la implementación Python original no es normalmente la más eficiente para producción en Windows.

---

## 1.5 faster-whisper

faster-whisper implementa Whisper sobre CTranslate2.

Repositorio:

* [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)

### Ventajas

* Gratuito.  
* Completamente local.  
* Compatible con español e inglés.  
* Funciona en CPU.  
* Puede aprovechar GPU NVIDIA.  
* Permite cuantización int8 en CPU.  
* Devuelve segmentos con timestamps.  
* Generalmente consume menos memoria y es más rápido que Whisper original.

### Limitaciones

* El primer uso descarga el modelo.  
* Los modelos ocupan espacio en disco.  
* En CPU, los videos largos pueden tardar varios minutos.  
* La calidad depende del modelo y del audio.  
* No resuelve por sí solo la descarga desde YouTube.

### Configuración recomendada

Para una máquina Windows sin GPU:

Python

WhisperModel(  
    "small",  
    device\="cpu",  
    compute\_type\="int8"

)

Si la calidad no es suficiente:

Python

WhisperModel(  
    "medium",  
    device\="cpu",  
    compute\_type\="int8"

)

Si hay una GPU NVIDIA correctamente configurada:

Python

WhisperModel(  
    "large-v3",  
    device\="cuda",  
    compute\_type\="float16"

)

Para el MVP usaría small multilingüe. No utilizaría un modelo terminado en .en, porque esos modelos son solo para inglés.

---

## 1.6 whisper.cpp

Otra alternativa gratuita:

* [ggerganov/whisper.cpp](https://github.com/ggerganov/whisper.cpp)

Puede resultar conveniente si se desea:

* Un binario independiente.  
* Menos dependencias Python.  
* Ejecución controlada en CPU.  
* Modelos cuantizados.

Para vuestro stack Python, faster-whisper es más sencillo de integrar. whisper.cpp quedaría como alternativa si CTranslate2 presenta problemas en Windows.

---

## 1.7 Servicios externos gratuitos

No encontré un servicio externo que reúna simultáneamente estas propiedades:

* Gratuito sin límites relevantes.  
* Estable.  
* Sin API key.  
* Que procese videos sin captions.  
* Apto para producción.  
* Sin riesgo de desaparecer o cambiar sus condiciones.

Los servicios que ofrecen ASR o extracción suelen funcionar con créditos, límites o planes de pago. Por tanto, no cumplen el requisito de una solución 100% gratuita.

---

## 1.8 Clientes de NotebookLM

No recomiendo integrar clientes no oficiales de NotebookLM como base del sistema.

Problemas:

* Usan cookies o sesiones de Google.  
* Pueden romperse con cambios internos.  
* La sesión puede caducar.  
* Riesgo de verificaciones o bloqueos.  
* Difícil ejecución desatendida.  
* No proporcionan un contrato estable.

Pueden servir para una prueba personal, pero no para una tool central de OpenCode.

---

# 2\. Distinción importante: audio frente a contenido visual

Una transcripción permite analizar:

* Lo que dicen los participantes.  
* Temas y conceptos.  
* Resúmenes.  
* Preguntas y respuestas.  
* Menciones concretas.  
* Capítulos aproximados.  
* Comparaciones y conclusiones.

Pero no permite analizar completamente:

* Diapositivas sin narración.  
* Código mostrado en pantalla.  
* Diagramas.  
* Gráficos.  
* Acciones físicas.  
* Texto que aparece visualmente.  
* Demostraciones silenciosas.

Por tanto, propongo dos niveles.

## Nivel 1: análisis del contenido hablado

Es el MVP y cubre la mayoría de tutoriales, podcasts, entrevistas y presentaciones:

text

captions → audio/Whisper → transcript → OpenCode

## Nivel 2: análisis multimodal

Opcionalmente:

text

video  
  ├── transcripción del audio  
  ├── extracción de frames relevantes  
  ├── OCR sobre frames

  └── modelo visual local

Para mantener todo gratis se podrían usar:

* FFmpeg u OpenCV para extraer frames.  
* PaddleOCR o Tesseract para texto en pantalla.  
* Ollama con un modelo visual local compatible, si el hardware lo soporta.

No incluiría este nivel en la primera versión porque aumenta considerablemente CPU, RAM, almacenamiento y complejidad.

---

# 3\. Arquitectura recomendada

text

OpenCode  
    │  
    │ MCP  
    ▼  
brain-ai-01 / FastAPI  
    │  
    ▼  
YouTubeService  
    │  
    ├── 1\. Validar y normalizar URL  
    ├── 2\. Buscar en caché  
    ├── 3\. Intentar youtube-transcript-api  
    ├── 4\. Intentar subtítulos mediante yt-dlp  
    ├── 5\. Descargar únicamente audio  
    ├── 6\. Transcribir con faster-whisper  
    ├── 7\. Guardar segmentos y timestamps

    └── 8\. Exponer el resultado mediante MCP

## Componentes

### Servidor MCP existente

Se añadirían inicialmente tres tools:

text

youtube\_transcript  
youtube\_transcript\_status

youtube\_transcript\_read

Y posteriormente:

text

youtube\_transcript\_search

### Caché y cola

Para una instalación sencilla en Windows:

* SQLite.  
* Un directorio de almacenamiento.  
* Un proceso worker separado.  
* Sin Redis.  
* Sin PostgreSQL.  
* Sin servicios externos.

### Archivos temporales

text

data/  
├── youtube.db  
├── transcripts/  
│   └── VIDEO\_ID.es.json  
├── models/  
└── temp/

El audio se elimina cuando termina la transcripción. La transcripción sí puede conservarse para evitar procesar dos veces el mismo video.

---

# 4\. Tools MCP propuestas

## youtube\_transcript

Busca captions y, si no existen, puede iniciar una transcripción local.

Entrada:

JSON

{  
  "url": "https://www.youtube.com/watch?v=VIDEO\_ID",  
  "languages": \["es", "en"\],  
  "allow\_asr": true,  
  "include\_timestamps": true

}

Respuesta inmediata si existen captions:

JSON

{  
  "status": "completed",  
  "video\_id": "VIDEO\_ID",  
  "title": "Título",  
  "language": "es",  
  "source": "youtube\_generated\_captions",  
  "transcript\_id": "VIDEO\_ID-es",  
  "segments": \[  
    {  
      "start": 0.5,  
      "end": 4.2,  
      "text": "Contenido del segmento"  
    }  
  \]

}

Si necesita Whisper y el proceso tardará demasiado:

JSON

{  
  "status": "processing",  
  "job\_id": "c35587cb-...",  
  "strategy": "faster\_whisper"

}

---

## youtube\_transcript\_status

JSON

{  
  "job\_id": "c35587cb-..."  
}

Respuesta:

JSON

{  
  "status": "processing",  
  "progress": 42

}

O:

JSON

{  
  "status": "completed",  
  "transcript\_id": "VIDEO\_ID-es"

}

---

## youtube\_transcript\_read

Evita enviar una transcripción de dos horas en una sola respuesta MCP.

Entrada:

JSON

{  
  "transcript\_id": "VIDEO\_ID-es",  
  "start\_seconds": 600,  
  "end\_seconds": 900,  
  "max\_chars": 20000

}

---

## youtube\_transcript\_search

Permite que OpenCode busque solo las partes relevantes:

JSON

{  
  "transcript\_id": "VIDEO\_ID-es",  
  "query": "¿Qué menciona sobre la autenticación?",  
  "limit": 8

}

La primera implementación puede utilizar SQLite FTS5, que es gratuito y no necesita embeddings.

---

# 5\. Implementación base

## Dependencias

txt

youtube-transcript-api  
yt-dlp  
faster-whisper

También conviene instalar FFmpeg.

En Windows:

PowerShell

winget install Gyan.FFmpeg

O mediante Chocolatey:

PowerShell

choco install ffmpeg

Instalación Python:

PowerShell

pip install youtube-transcript-api yt-dlp faster-whisper

No fijaría versiones antes de probarlas con la versión de Python utilizada por brain-ai-01. Una vez validado el conjunto, sí se deben fijar las versiones en requirements.txt o pyproject.toml.

---

# 6\. Servicio de extracción inicial

El siguiente código muestra el núcleo de la solución. Habría que adaptarlo a la estructura exacta de brain-ai-01.

Python

\# services/youtube\_service.py

from \_\_future\_\_ import annotations

import asyncio  
import json  
import re  
import tempfile  
from dataclasses import asdict, dataclass  
from pathlib import Path  
from urllib.parse import parse\_qs, urlparse

from faster\_whisper import WhisperModel  
from youtube\_transcript\_api import YouTubeTranscriptApi

YOUTUBE\_HOSTS \= {  
    "youtube.com",  
    "www.youtube.com",  
    "m.youtube.com",  
    "youtu.be",  
    "www.youtu.be",  
}

@dataclass  
class TranscriptSegment:  
    start: float  
    end: float  
    text: str

@dataclass  
class TranscriptResult:  
    video\_id: str  
    language: str | None  
    source: str  
    segments: list\[TranscriptSegment\]

    @property  
    def text(self) \-\> str:  
        return "\\n".join(segment.text for segment in self.segments)

    def to\_dict(self) \-\> dict:  
        result \= asdict(self)  
        result\["text"\] \= self.text  
        return result

def extract\_video\_id(url: str) \-\> str:  
    parsed \= urlparse(url.strip())

    if parsed.scheme not in {"http", "https"}:  
        raise ValueError("La URL debe utilizar HTTP o HTTPS")

    host \= parsed.hostname.lower() if parsed.hostname else ""

    if host not in YOUTUBE\_HOSTS:  
        raise ValueError("El host no pertenece a YouTube")

    if host in {"youtu.be", "www.youtu.be"}:  
        video\_id \= parsed.path.strip("/").split("/")\[0\]  
    elif parsed.path \== "/watch":  
        video\_id \= parse\_qs(parsed.query).get("v", \[""\])\[0\]  
    elif parsed.path.startswith("/shorts/"):  
        video\_id \= parsed.path.split("/")\[2\]  
    elif parsed.path.startswith("/embed/"):  
        video\_id \= parsed.path.split("/")\[2\]  
    else:  
        raise ValueError("Formato de URL de YouTube no reconocido")

    if not re.fullmatch(r"\[A-Za-z0-9\_-\]{11}", video\_id):  
        raise ValueError("ID de video inválido")

    return video\_id

class YouTubeService:  
    def \_\_init\_\_(  
        self,  
        model\_name: str \= "small",  
        device: str \= "cpu",  
        compute\_type: str \= "int8",  
    ):  
        self.\_model\_name \= model\_name  
        self.\_device \= device  
        self.\_compute\_type \= compute\_type  
        self.\_whisper\_model: WhisperModel | None \= None

    def \_get\_whisper\_model(self) \-\> WhisperModel:  
        if self.\_whisper\_model is None:  
            self.\_whisper\_model \= WhisperModel(  
                self.\_model\_name,  
                device\=self.\_device,  
                compute\_type\=self.\_compute\_type,  
            )

        return self.\_whisper\_model

    async def get\_transcript(  
        self,  
        url: str,  
        languages: list\[str\] | None \= None,  
        allow\_asr: bool \= True,  
    ) \-\> TranscriptResult:  
        languages \= languages or \["es", "en"\]  
        video\_id \= extract\_video\_id(url)

        try:  
            return await asyncio.to\_thread(  
                self.\_fetch\_youtube\_captions,  
                video\_id,  
                languages,  
            )  
        except Exception as caption\_error:  
            if not allow\_asr:  
                raise RuntimeError(  
                    f"No fue posible obtener captions: {caption\_error}"  
                ) from caption\_error

        audio\_path \= await self.\_download\_audio(url)

        try:  
            return await asyncio.to\_thread(  
                self.\_transcribe\_audio,  
                video\_id,  
                audio\_path,  
            )  
        finally:  
            audio\_path.unlink(missing\_ok\=True)

    def \_fetch\_youtube\_captions(  
        self,  
        video\_id: str,  
        languages: list\[str\],  
    ) \-\> TranscriptResult:  
        api \= YouTubeTranscriptApi()  
        transcript \= api.fetch(video\_id, languages\=languages)

        segments \= \[\]

        for item in transcript:  
            start \= float(item.start)  
            duration \= float(item.duration)

            segments.append(  
                TranscriptSegment(  
                    start\=start,  
                    end\=start \+ duration,  
                    text\=item.text.strip(),  
                )  
            )

        return TranscriptResult(  
            video\_id\=video\_id,  
            language\=getattr(transcript, "language\_code", None),  
            source\="youtube\_captions",  
            segments\=segments,  
        )

    async def \_download\_audio(self, url: str) \-\> Path:  
        temp\_dir \= Path(tempfile.mkdtemp(prefix\="brain-ai-youtube-"))  
        output\_template \= str(temp\_dir / "audio.%(ext)s")

        process \= await asyncio.create\_subprocess\_exec(  
            "yt-dlp",  
            "--no-playlist",  
            "--no-progress",  
            "--format",  
            "bestaudio/best",  
            "--output",  
            output\_template,  
            "--print",  
            "after\_move:filepath",  
            url,  
            stdout\=asyncio.subprocess.PIPE,  
            stderr\=asyncio.subprocess.PIPE,  
        )

        stdout, stderr \= await process.communicate()

        if process.returncode \!= 0:  
            error \= stderr.decode("utf-8", errors\="replace")  
            raise RuntimeError(f"yt-dlp no pudo descargar el audio: {error}")

        lines \= stdout.decode("utf-8", errors\="replace").strip().splitlines()

        if not lines:  
            raise RuntimeError("yt-dlp no devolvió la ruta del audio")

        audio\_path \= Path(lines\[\-1\].strip())

        if not audio\_path.exists():  
            raise RuntimeError("No se encontró el audio descargado")

        return audio\_path

    def \_transcribe\_audio(  
        self,  
        video\_id: str,  
        audio\_path: Path,  
    ) \-\> TranscriptResult:  
        model \= self.\_get\_whisper\_model()

        generated\_segments, info \= model.transcribe(  
            str(audio\_path),  
            language\=None,  
            beam\_size\=5,  
            vad\_filter\=True,  
        )

        segments \= \[  
            TranscriptSegment(  
                start\=float(segment.start),  
                end\=float(segment.end),  
                text\=segment.text.strip(),  
            )  
            for segment in generated\_segments  
            if segment.text.strip()  
        \]

        return TranscriptResult(  
            video\_id\=video\_id,  
            language\=info.language,  
            source\="faster\_whisper",  
            segments\=segments,

        )

Este ejemplo implementa:

* Validación de URL.  
* Captions como primera opción.  
* Descarga de audio como fallback.  
* Whisper local.  
* Español e inglés.  
* Timestamps.  
* Sin servicios de pago.  
* Ejecución segura sin shell=True.

Faltaría añadir:

* Caché.  
* Límite de duración.  
* Extracción de subtítulos con yt-dlp antes de descargar audio.  
* Persistencia de jobs.  
* Errores estructurados.  
* Limpieza del directorio temporal completo.  
* Métricas y logs.

---

# 7\. Integración MCP

Si mcp\_bridge.py utiliza FastMCP, conceptualmente sería:

Python

from services.youtube\_service import YouTubeService

youtube\_service \= YouTubeService(  
    model\_name\="small",  
    device\="cpu",  
    compute\_type\="int8",  
)

@mcp.tool()  
async def youtube\_transcript(  
    url: str,  
    languages: list\[str\] | None \= None,  
    allow\_asr: bool \= True,  
) \-\> dict:  
    """  
    Extrae o genera la transcripción de un video público de YouTube.

    Primero intenta captions de YouTube. Si no existen y allow\_asr=true,  
    descarga solo el audio y lo transcribe localmente con faster-whisper.  
    """  
    result \= await youtube\_service.get\_transcript(  
        url\=url,  
        languages\=languages or \["es", "en"\],  
        allow\_asr\=allow\_asr,  
    )

    return result.to\_dict()

Sin embargo, esto solo es apropiado para videos cortos. Una transcripción de 30–90 minutos puede superar el timeout de la llamada MCP.

Para producción debe usarse:

text

youtube\_transcript\_start  
youtube\_transcript\_status

youtube\_transcript\_read

El primer tool crea un job, el worker lo procesa y el segundo consulta su estado.

---

# 8\. Cola gratuita con SQLite

No hace falta Redis o Celery para la primera versión.

Tabla básica:

SQL

CREATE TABLE youtube\_jobs (  
    id TEXT PRIMARY KEY,  
    video\_id TEXT NOT NULL,  
    url TEXT NOT NULL,  
    status TEXT NOT NULL,  
    progress INTEGER NOT NULL DEFAULT 0,  
    result\_path TEXT,  
    error TEXT,  
    created\_at TEXT NOT NULL,  
    updated\_at TEXT NOT NULL

);

Estados:

text

pending  
extracting\_captions  
downloading\_audio  
transcribing  
completed

failed

Funcionamiento:

text

FastAPI/MCP  
    └── inserta el job y devuelve job\_id

Worker Python  
    ├── reclama un job pending  
    ├── obtiene captions o audio  
    ├── transcribe  
    ├── guarda JSON

    └── actualiza el estado

Esto es gratuito, durable y funciona en Windows.

---

# 9\. Cómo analizar videos largos sin llenar el contexto

No conviene devolver al modelo una transcripción completa de dos horas.

La transcripción debe dividirse en fragmentos:

JSON

{  
  "video\_id": "abc123",  
  "chunk\_index": 12,  
  "start": 620.5,  
  "end": 684.2,  
  "text": "Contenido del fragmento..."

}

Configuración práctica:

* 500–1.000 tokens por chunk.  
* 10–15% de solapamiento.  
* Mantener timestamps.  
* No cortar frases cuando sea posible.

La búsqueda inicial puede realizarse con SQLite FTS5:

SQL

CREATE VIRTUAL TABLE transcript\_chunks\_fts USING fts5(  
    transcript\_id,  
    text,  
    content\=''

);

OpenCode podría ejecutar:

text

youtube\_transcript\_search(  
    transcript\_id="...",  
    query="problemas de autenticación"

)

Y recibir únicamente los fragmentos relevantes.

Las respuestas deberían citar el momento exacto:

text

https://www.youtube.com/watch?v=VIDEO\_ID\&t=620s

---

# 10\. Análisis visual opcional y gratuito

Si “analizar el contenido” incluye lo que aparece en pantalla, se puede extender el pipeline.

## Extracción de frames

FFmpeg permite detectar cambios de escena:

PowerShell

ffmpeg \-i video.mp4 \`  
  \-vf "select='gt(scene,0.30)',scale=1280:-1" \`

  \-vsync vfr frames/frame-%05d.jpg

También se puede extraer un frame cada cierto tiempo:

PowerShell

ffmpeg \-i video.mp4 \-vf "fps=1/30,scale=1280:-1" frames/frame-%05d.jpg

## OCR

Alternativas gratuitas:

* [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)  
* [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)

PaddleOCR suele ser más conveniente para screenshots, diapositivas e interfaces.

## Modelo visual local

Podría desplegarse un modelo visual mediante Ollama, siempre que la máquina tenga RAM/GPU suficiente.

Flujo:

text

frame  
  ├── OCR → texto visible  
  └── modelo visual → descripción

texto visual \+ descripción \+ transcript  
                ↓

             OpenCode

No lo incluiría en el MVP. Primero implementaría transcripción; después OCR; finalmente un modelo visual local si realmente se necesita.

---

# 11\. Riesgos y mitigaciones

## Bloqueos de YouTube

No existe una solución gratuita capaz de garantizar acceso a todos los videos. YouTube puede bloquear la IP o exigir mecanismos adicionales.

Mitigaciones:

* Cachear resultados por video e idioma.  
* Limitar concurrencia.  
* Usar reintentos con backoff.  
* Mantener yt-dlp actualizado.  
* No procesar repetidamente el mismo video.  
* Diferenciar “sin captions” de “IP bloqueada”.  
* Ejecutar primero desde vuestra máquina Windows si tiene una IP residencial.  
* No usar proxies gratuitos: son inseguros e inestables.

## Videos privados o restringidos

La primera versión debe aceptar solamente:

* Videos públicos.  
* Sin autenticación.  
* Sin cookies.  
* Sin playlists.

No recomiendo guardar cookies de una cuenta de Google en el servidor.

## Uso abusivo

Aplicar:

* Duración máxima, por ejemplo 2 horas.  
* Máximo de jobs concurrentes.  
* Timeout de descarga.  
* Máximo de espacio temporal.  
* Eliminación automática de audio.  
* Rechazo de streams en directo.  
* Rechazo inicial de playlists.

## Seguridad

* Validar el host y el ID.  
* No aceptar parámetros arbitrarios de yt-dlp.  
* Nunca usar shell=True.  
* Utilizar directorios temporales.  
* No permitir que el usuario controle la ruta de salida.  
* Limitar la duración antes de descargar.  
* No devolver rutas internas del servidor.

## Mantenimiento

Tanto youtube-transcript-api como yt-dlp dependen de mecanismos no oficiales.

Debe existir una interfaz de proveedores:

Python

class TranscriptProvider:  
    async def fetch(self, request):

        raise NotImplementedError

Implementaciones:

text

YouTubeTranscriptProvider  
YtDlpSubtitleProvider

FasterWhisperProvider

Así se puede reemplazar un proveedor sin modificar las tools MCP.

## Aspectos legales

Descargar y procesar audio puede estar sujeto a los términos de YouTube y a copyright.

Medidas prudentes:

* Procesar solo bajo petición.  
* No redistribuir el video o audio.  
* Eliminar el audio al finalizar.  
* Conservar solo la transcripción si es necesario.  
* Informar al usuario de que debe tener derecho a procesar el contenido.

---

# 12\. Plan concreto de implementación

## Fase 1: captions

Implementar:

* Parser de URLs.  
* youtube-transcript-api.  
* Timestamps.  
* Idiomas es y en.  
* Caché SQLite.  
* Tool MCP youtube\_transcript.

Resultado: rápido y suficiente para videos con captions.

## Fase 2: fallback local

Añadir:

* yt-dlp.  
* Inspección de subtítulos.  
* Descarga de audio.  
* faster-whisper.  
* Worker local.  
* Jobs persistentes.  
* Tools de inicio y estado.

Resultado: funcionamiento con videos sin captions.

## Fase 3: análisis eficiente

Añadir:

* Chunking.  
* SQLite FTS5.  
* Búsqueda de fragmentos.  
* Resúmenes por secciones.  
* Citas con timestamps.

Resultado: experiencia parecida a NotebookLM para preguntas sobre el contenido hablado.

## Fase 4: contenido visual

Añadir:

* Descarga de una versión de baja resolución.  
* Extracción de frames por cambios de escena.  
* PaddleOCR.  
* Modelo visual local opcional.

Resultado: análisis de diapositivas, código y elementos visuales.

---

# Recomendación final

Implementaría esta solución:

text

1\. youtube-transcript-api  
2\. yt-dlp para subtítulos  
3\. yt-dlp para descargar solo audio  
4\. faster-whisper local  
5\. SQLite para caché, jobs y búsqueda  
6\. Tools MCP para iniciar, consultar, leer y buscar

7\. OpenCode analiza los fragmentos recuperados

Es la opción que mejor cumple los requisitos:

* Funciona en Windows.  
* Se integra directamente con Python/FastAPI/MCP.  
* No usa APIs de pago.  
* Soporta español e inglés.  
* Funciona con videos sin captions.  
* No depende de NotebookLM ni de cookies de Google.  
* Puede ampliarse posteriormente para contenido visual.

La limitación inevitable es que ninguna solución gratuita basada en YouTube puede garantizar el 100% de los videos debido a bloqueos, restricciones regionales, contenido privado y cambios internos de la plataforma. Para videos públicos normales, el pipeline captions → yt-dlp → faster-whisper es la solución gratuita más sólida.  
