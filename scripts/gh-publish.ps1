<#
  gh-publish.ps1 - Crea (y opcionalmente mergea) un PR de una rama a su base usando gh CLI.

  Requisitos:
    - git + gh CLI instalados
    - Autenticacion UNA vez con PAT (ver docs/CONFIG_API_TOKEN_PASO_A_PASO.md):
      variable de entorno User GH_TOKEN, o `gh auth login --with-token`
    - Ejecutar desde la raiz del repositorio

  Uso:
    .\gh-publish.ps1                                        # crea PR develop -> main
    .\gh-publish.ps1 -Merge                                 # crea PR y lo mergea (cero clics)
    .\gh-publish.ps1 -Rama feature/x                        # publica otra rama a main
    .\gh-publish.ps1 -Rama feature/x -Base develop -Merge   # PR feature/x -> develop + merge
    .\gh-publish.ps1 -Repo usuario/repo                     # apunta a otro repositorio

  OBLIGATORIO para el agente: NUNCA usar `gh pr create` / `gh pr merge`
  directos. Todo PR y merge pasa por este script.
#>

param(
    [string]$Rama = "develop",
    [string]$Base = "main",
    [switch]$Merge,
    [string]$Repo = "",
    [string]$Titulo = ""
)

# 'Continue' para que el stderr de comandos nativos (gh/git) no se convierta
# en error terminante; todos los fallos se chequean via $LASTEXITCODE.
$ErrorActionPreference = "Continue"

function Exit-WithError([string]$Mensaje) {
    Write-Host "ERROR: $Mensaje" -ForegroundColor Red
    exit 1
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Exit-WithError "gh CLI no esta instalado. Instalar: winget install GitHub.cli"
}

# Credencial: si el proceso no heredo GH_TOKEN (abierto antes de crearla),
# auto-cargarla desde variables de entorno User. Nunca se imprime el valor.
if (-not $env:GH_TOKEN) {
    $env:GH_TOKEN = [Environment]::GetEnvironmentVariable("GH_TOKEN", "User")
}

& gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    Exit-WithError "gh no autenticado. Ejecutar UNA vez: gh auth login --hostname github.com --git-protocol https --with-token"
}

git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
    Exit-WithError "no es un repositorio git (ejecutar desde la raiz del repo)"
}

$extra = @()
if ($Repo) { $extra = @("--repo", $Repo) }

# 1) Subir la rama actual
git push -u origin $Rama 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Exit-WithError "no se pudo pushear la rama '$Rama'"
}

# 2) Buscar PR abierto existente (Rama -> Base)
$listArgs = @("pr", "list", "--head", $Rama, "--base", $Base, "--json", "url", "--jq", ".[0].url") + $extra
$prUrl = (& gh @listArgs 2>$null | Out-String).Trim()
if ($prUrl -eq "null") { $prUrl = "" }

# 3) Crear PR si no existe
if (-not $prUrl) {
    if (-not $Titulo) { $Titulo = "Publish $Rama to $Base" }
    $body = "Publicacion automatica de '$Rama' a '$Base' ($(Get-Date -Format 'yyyy-MM-dd'))."
    $createArgs = @("pr", "create", "--base", $Base, "--head", $Rama, "--title", $Titulo, "--body", $body) + $extra
    $out = & gh @createArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        $err = ($out | Out-String)
        if ($err -match "no commits between|No commits between") {
            Write-Host "No hay cambios pendientes: '$Rama' ya esta al dia con $Base." -ForegroundColor Yellow
            exit 0
        }
        Exit-WithError ("no se pudo crear el PR: " + $err.Trim())
    }
    $prUrl = (& gh @listArgs 2>$null | Out-String).Trim()
    if (-not $prUrl -or $prUrl -eq "null") {
        Exit-WithError "el PR se creo pero no se pudo obtener la URL"
    }
    Write-Host "PR creado: $prUrl" -ForegroundColor Green
} else {
    Write-Host "PR existente: $prUrl" -ForegroundColor Cyan
}

# 4) Merge opcional
if ($Merge) {
    $mergeArgs = @("pr", "merge", $prUrl, "--merge") + $extra
    $out = & gh @mergeArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        Exit-WithError ("no se pudo mergear: " + ($out | Out-String).Trim())
    }
    Write-Host "Merge completado en $Base. Si es main, GitHub Pages se despliega automaticamente." -ForegroundColor Green
} else {
    Write-Host "Siguiente paso: mergear el PR en GitHub, o re-ejecutar con -Merge." -ForegroundColor Yellow
}