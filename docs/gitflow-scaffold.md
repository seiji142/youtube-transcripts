# Template: Setup de Proyecto — Git Flow + GitHub Pages + opencode/MCP

> **Fuente de verdad:** repo privado `seiji142/gitflow-scaffold`
> (https://github.com/seiji142/gitflow-scaffold), **versión aplicada
> `2026.09.25`** (25/09/2026). La carpeta local
> `Proyecto AI/templates/gitflow-scaffold` queda solo como espejo del
> `scripts/gh-publish.ps1` — el resto puede estar desincronizado.
>
> **Adaptación a youtube-transcripts (23/09/2026, actualizada 25/09):**
> copia del `TEMPLATE_GITFLOW_GH_PAGES.md` como referencia. Aplicado:
> estructura de ramas (§1-2,§6-7), `.ai/context.md` con "Ramas del
> Proyecto", `opencode.json` ya resuelto (no copiado); **25/09:**
> `scripts/gh-publish.ps1` con `-Base`, `.ai/commands.md` con
> validación pre-PR (variante B) + Publicación vía script, y
> `.github/workflows/ci.yml` (Python, pytest sin red). **NO aplica:**
> §3 GitHub Pages / `deploy.yml` / build npm — este repo es Python/MCP
> sin sitio estático (decisión Q1 en `docs/DECISIONES.md`); `ci.yml`
> del template adaptado de Node a Python. `master` = legacy congelada
> (Q2). Rama de trabajo: `develop` (creada 23/09 desde `origin/main`).

Guía replicable para configurar un proyecto nuevo con:

1. Estructura de ramas Git (main / develop / feature).
2. Deploy estático a GitHub Pages con CI.
3. Integración del asistente IA (opencode + MCP + memoria persistente).

Adapta los `<PLACEHOLDERS>` al proyecto concreto.

---

## 1. Estructura de ramas

| Rama | Proposito | Sale de | Vuelve a | Proteccion |
|------|-----------|---------|----------|------------|
| `main` | Produccion · deploy GitHub Pages | — | — | Requiere PR (sin push directo) |
| `develop` | Desarrollo diario (rama por defecto) | `main` | `main` (PR al publicar) | No |
| `feature/<desc>` | Cada tarea o experimento | `develop` | `develop` (PR) | No |

Reglas de comportamiento:
- Trabajar SIEMPRE en `develop`. Antes de modificar, verificar la rama actual con
  `git status`/`git branch`; si se esta en `main`, no trabajar ahi.
- `main` solo se toca para publicar, via PR desde `develop`. El deploy de
  GitHub Pages se dispara con el merge a `main`.
- Tareas grandes o experimentos: crear `feature/<desc>` desde `develop` y
  mergear de vuelta a `develop`.

## 2. Setup inicial (fases)

### Fase 1 — Crear rama de desarrollo
```bash
git checkout -b develop          # desde main
git push -u origin develop       # tracking
```

### Fase 2 — Documentar el flujo
- Agregar en `.ai/context.md` una seccion "Ramas del Proyecto" con la tabla
  anterior y las reglas de comportamiento.
- Guardar en memoria persistente:
  `brain_ai_memory_save(project="<PROYECTO>", decision="Rama de desarrollo por defecto = develop; main = produccion; feature/* para tareas", tags=["git", "flujo-trabajo", "branching"])`.

### Fase 3 — Proteccion de `main` en GitHub (manual)
En GitHub → Settings → Branches → **Add classic branch protection rule**:
- Branch name pattern: `main`
- Marcar **"Require a pull request before merging"**
- **NO marcar "Require approvals"** (ver advertencia abajo)
- Create

Consecuencia: con proteccion activa no hay push directo a `main`; publicar =
PR desde `develop`, sin necesidad de review.

> **ADVERTENCIA (leccion real):** en un repositorio 100% personal, **el autor de
> un PR no puede aprobar su propio PR** ("Los autores de las solicitudes de
> extracción no pueden aprobar sus propias solicitudes de extracción"). Si marcas
> "Require approvals", no habra nadie con acceso `write` para aprobar y el PR
> queda bloqueado permanentemente. Por eso: **PR obligatorio SIN Require
> approvals**. Solo marcar approvals si hay colaboradores con acceso `write`.

### Fase 4 — Verificacion final
```bash
git branch -a   # debe mostrar main, develop, origin/develop, origin/main
git status      # working tree limpio
```

### Fase 5 — Autenticar `gh` con token (opcional, para PRs vía CLI)

> **Estado en este proyecto (25/09/2026): completa.** Paso 0 del usuario
> hecho (PAT con `seiji142/youtube-transcripts` + Contents/PRs RW):
> `gh auth status` OK, `gh pr list` exit 0 y **PR #1 creado real**
> (`develop → main`, 5 commits, MERGEABLE, sin mergear) — escritura
> verificada. Merge pendiente de decisión de publicar.
> Playbook validado: `templates/gitflow-scaffold/CONFIG_API_TOKEN_PASO_A_PASO.md`
> (25/09/2026, proyecto portfolio).

Con `main` protegido (PR obligatorio), la CLI permite crear/mergear PRs sin
abrir la UI. SSH y el token de API son **capas distintas**: SSH autentica
git push/pull; el token autentica la API REST de GitHub (PRs, settings,
lectura de protección). SSH **no** sustituye al token.

#### Paso 0 — Ampliar el PAT existente (en GitHub, manual; sin secretos)

El `GH_TOKEN` vigente es el PAT fine-grained de portfolio (*Only select
repositories*). En vez de crear otro token: GitHub → avatar →
**Settings** → **Developer settings** → **Personal access tokens** →
**Fine-grained tokens** → el token → *Repository access → Only select
repositories* → **agregar `seiji142/youtube-transcripts`** → verificar
permisos (*Contents* RW, *Pull requests* RW, ideal +*Actions* R) →
**Update token**. El valor **no cambia**: `GH_TOKEN` sigue válido, nada
que pegar en ningún lado.

#### A. Crear un token nuevo (solo si el Paso 0 no aplica)

1. GitHub → avatar → **Settings** → **Developer settings** (izquierda, abajo)
   → **Personal access tokens**.
2. **Recomendado: Fine-grained token** (*Generate new token → Fine-grained*):
   - **Repository access:** solo `seiji142/youtube-transcripts` (mínimo privilegio).
   - **Permissions → Repository permissions:**
     - *Contents:* **Read and write** (para mergear)
     - *Pull requests:* **Read and write** (crear/mergear PRs)
     - *Actions:* **Read** (ver deploys con `gh run list`)
   - **Expiration:** 90 días (o la que prefieras).
3. *(Alternativa clásica: token classic con scope `repo` — da más permisos de los necesarios.)*
4. Copiar el token apenas lo genera (solo se muestra una vez), y guardarlo
   en terminal propia (nunca en el chat):
   `[Environment]::SetEnvironmentVariable("GH_TOKEN", "<tu token>", "User")`

#### B. Autenticar `gh` (terminal)

```powershell
# Opción 1 — pegarlo en gh (no queda en el historial de comandos):
gh auth login
#   Where do you use GitHub?          → GitHub.com
#   Preferred protocol for Git ops    → SSH (o HTTPS si no usás claves SSH)
#   Authenticate Git with GH creds?   → Yes
#   How to authenticate?              → Paste an authentication token
#   (pegás el token + Enter)

# Opción 2 — variable de entorno GH_TOKEN (persiste en nuevas terminales):
[Environment]::SetEnvironmentVariable("GH_TOKEN", "<PEGAR_TOKEN_AQUÍ>", "User")
```

#### C. Verificar (sin revelar el valor)

```powershell
# GH_TOKEN existe a nivel User pero el proceso abierto antes no la hereda:
# auto-cargarla (los scripts del repo ya lo hacen solos)
if (-not $env:GH_TOKEN) {
    $env:GH_TOKEN = [Environment]::GetEnvironmentVariable("GH_TOKEN", "User")
}
gh auth status
gh pr list --repo seiji142/youtube-transcripts
# Detalle de protección: la API anónima ya probó protected=true (23/09);
# con este PAT da 403 porque leer branch protection exige el permiso
# Administration (read), que se omite a propósito (mínimo privilegio).
# Opcional: agregarlo al PAT si algún día hace falta el detalle vía CLI.
```

#### D. Script `scripts/gh-publish.ps1` (cero fricción)

Copiado del template con una adaptación (sin mensaje de GitHub Pages;
este repo es Python/MCP). Sin secretos: lee `GH_TOKEN` del registro
en runtime.

```powershell
.\scripts\gh-publish.ps1           # crea PR develop -> main
.\scripts\gh-publish.ps1 -Merge    # crea PR y lo mergea (cero clics)
```

#### Gotchas (del playbook validado 25/09 + LECCIONES)

- Procesos abiertos antes de crear `GH_TOKEN` no la heredan → el
  script la auto-carga; nunca imprimir su valor (verificar con
  `gh auth status`).
- **403 `Resource not accessible by personal access token`**:
  lectura OK + escritura 403 = permisos del token; **lectura 403 en
  repo público = el repo no está en *Repository access*** (o token
  vencido) — ver LECCIONES 25/09. Se corrige con *Update token* sin
  cambiar el valor.
- Expiración (90 días): repetir Paso 0/A; única fricción recurrente.

#### Reglas de seguridad (obligatorias)

- El token **nunca** en el chat, en commits, ni en archivos del repo.
- SSH queda para git; el token solo para la API — se complementan, no compiten.
- Revocación: GitHub → Settings → Developer settings → el token → *Delete*.

## 3. Deploy a GitHub Pages

### 3.1 Requisitos de codigo
- Compilar a HTML autocontenido (opcional: `vite-plugin-singlefile`).
- En la config de build agregar base relativa, ej. Vite:
  ```ts
  export default defineConfig({
    base: "./",
    // ...
  });
  ```
- Usar rutas RELATIVAS (sin `/` inicial) para assets publicos, imagenes en data
  y enlaces a archivos estaticos (ej. CV). Asi el sitio funciona bajo cualquier
  subruta (`https://<usuario>.github.io/<repo>/`).

### 3.2 Workflow CI — `.github/workflows/deploy.yml`
```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: <SUB_PROYECTO>/package-lock.json
      - name: Install dependencies
        working-directory: <SUB_PROYECTO>
        run: npm ci
      - name: Build
        working-directory: <SUB_PROYECTO>
        run: npm run build
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: <SUB_PROYECTO>/dist

  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```
Donde `<SUB_PROYECTO>` es la carpeta del proyecto dentro del repo (o `.` si el
repo es solo el sitio). Nota: monorepos usan `working-directory` y
`cache-dependency-path` apuntando a la subcarpeta.

### 3.3 Paso manual (unico)
GitHub → repositorio → Settings → Pages → Source: **GitHub Actions**.
(Se puede activar antes o despues del primer push; hasta entonces no se publica.)
El push/merge a `main` dispara el build + deploy automatico.

> **Error tipico (leccion real):** si el workflow corre con Pages deshabilitado
> (o en modo "Deploy from a branch"), el job `deploy` falla con
> `Get Pages site failed... Not Found`. Solucion:
> 1. Confirmar Settings → Pages → Source: **GitHub Actions** (no "Deploy from a branch").
> 2. En Actions → "Deploy to GitHub Pages" → **Re-run all jobs**.
> 3. Si persiste, forzar el enablement programatico en el workflow:
>    ```yaml
>    - uses: actions/configure-pages@v5
>      with:
>        enablement: true
>    ```

### 3.4 Resultado
Sitio publicado en `https://<usuario>.github.io/<repo>/`. El deploy se
regenera con cada push o merge a `main`.

## 4. Configuracion opencode / MCP

### 4.1 `opencode.json` de ejemplo
```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "<PROVEEDOR>/<MODELO>",
  "instructions": [
    ".ai/system.md",
    ".ai/rules.md",
    ".ai/context.md",
    ".ai/agents.md",
    ".ai/MEMORY.md"
  ],
  "permission": {
    "bash": "allow",
    "webfetch": "ask",
    "write": "ask",
    "edit": "ask"
  },
  "mcp": {
    "git_publisher": {
      "type": "local",
      "command": [
        "<RUTA_VENV>/Scripts/python.exe",
        "<RUTA_HERRAMIENTAS>/git_tool.py"
      ],
      "enabled": true
    },
    "brain-ai": {
      "type": "local",
      "command": ["python", "<RUTA>/brain-ai-01/mcp_bridge.py"],
      "enabled": true
    }
  }
}
```

### 4.2 Leccion aprendida sobre MCP
- **"connected" NO garantiza herramientas registradas.** Solo confirma el
  handshake inicial; las tools pueden fallar en `tools/list`.
- Fix comprobado: declarar el servidor MCP **explicitamente local** en el
  `opencode.json` del proyecto, con ruta absoluta del intérprete/venv propio,
  y **reiniciar OpenCode totalmente** (no basta nueva sesion).
- `permission.bash` no controla herramientas MCP.
- Para diagnosticar: probar el protocolo directamente (initialize →
  notifications/initialized → tools/list) en vez de confiar en la UI.

### 4.3 Leccion real: rutas relativas vs heuristica de emoji

**Sintoma:** las cards de proyectos mostradas como texto gigante en vez de
imagen (ej. aparecia `images/projects/portfolio-web.png` como "emoji").

**Causa:** la heuristica consideraba "imagen" solo si la ruta empezaba con `/`
o `http`. Con rutas RELATIVAS (`images/...`, sin `/` inicial) la clasificaba
como emoji.

```ts
// ANTES (roto con rutas relativas)
function isEmoji(str?: string) {
  return !!str && !str.startsWith("http") && !str.startsWith("/");
}
```

**Fix probado:** detectar separadores de ruta y extension de imagen.

```ts
const IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg|avif|bmp|ico)$/i;

function isEmoji(str?: string) {
  return !!str && !/[\/\\]/.test(str) && !IMAGE_EXT.test(str);
}
```

Cubre: rutas relativas (`images/...`), absolutas (`/...`) y URLs (`http...`)
→ imagen; emojis planos → emoji.

> Regla general: si el codigo distingue entre URL/emoji usando
> `startsWith("/")` o `startsWith("http")`, revisalo al migrar a rutas
> relativas.

## 5. Archivos `.ai/`
| Archivo | Contenido minimo |
|---------|------------------|
| `system.md` | Rol, tono, postura epistemica, reglas de memoria y uso de MCP |
| `rules.md` | Reglas de seguridad, idioma, calidad, verificacion obligatoria |
| `context.md` | Stack, arquitectura, convenciones, comandos y seccion "Ramas del Proyecto" |
| `agents.md` | Agentes especialistas y cuando activarlos |
| `MEMORY.md` | Instrucciones de memoria persistente y herramientas brain-ai |

## 6. Comandos del flujo diario
```bash
git checkout develop                       # trabajar en develop
git checkout -b feature/<desc> develop     # tarea o experimento
# ... trabajo ...
# merge de vuelta a develop (PR o local)
git checkout develop
git merge feature/<desc>
# publicar produccion: PR develop -> main (GitHub), que dispara el deploy
```

## 7. Checklist de verificacion
- [x] `develop` creada y subida con tracking (`origin/develop`).
- [x] `main` con branch protection (require PR, SIN require approvals).
- [x] `gh` autenticado (GH_TOKEN) — Fase 5 completa 25/09: `gh auth status`
      OK, PR #1 creado y mergeado con `scripts/gh-publish.ps1`.
- [x] `.github/workflows/ci.yml` (25/09): adaptado del template a Python
      (`setup-python` 3.10 + pytest sin red) en `main`/`develop`/`feature/*`.
- [x] **Check `build` requerido en `main`** (25/09): activado por el
      usuario en *Settings → Branches* (la UI es el camino: el PAT sin
      *Administration* da 403, nota del propio template). Verificación
      programática del detalle: 403 en `/branches/main/protection`;
      comprobación observable vía `mergeStateStatus` de un PR (bloqueado
      con CI pendiente → limpio con CI verde).
- [x] Flujo documentado en `.ai/context.md` y memoria persistente.
- N/A en este repo (Q1, sin Pages): base relativa, `npm run build`,
  heurística de emoji, Settings → Pages, sitio visible.