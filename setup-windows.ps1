#Requires -Version 5.1
<#
.SYNOPSIS
  Instala prerequisitos de AlejandrISBN en Windows: Brave, Git y Docker Desktop.

.DESCRIPTION
  Usa winget (incluido en Windows 10/11 recientes). Requiere administrador.
  Preferible lanzarlo con setup-windows.bat (pide elevacion automaticamente).

.NOTES
  Tras Docker Desktop suele hacer falta reiniciar el PC y abrir Docker Desktop
  una vez antes de usar start.bat.
#>

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "    OK: $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host "    AVISO: $Message" -ForegroundColor Yellow
}

function Write-Err([string]$Message) {
    Write-Host "    ERROR: $Message" -ForegroundColor Red
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-WingetSuccess([int]$Code) {
    # 0 = ok; -1978335189 = already installed; -1978335212 sometimes "no upgrade"
    return ($Code -eq 0) -or ($Code -eq -1978335189) -or ($Code -eq -1978335212)
}

function Install-WingetPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$DisplayName
    )

    Write-Step "Instalando $DisplayName ($Id)"

    $args = @(
        "install", "-e", "--id", $Id,
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity"
    )

    & winget @args
    $code = $LASTEXITCODE

    if (Test-WingetSuccess $code) {
        Write-Ok "$DisplayName listo (codigo winget: $code)"
        return $true
    }

    Write-Err "Fallo al instalar $DisplayName (codigo winget: $code)"
    return $false
}

# --- Prechecks ---------------------------------------------------------------

if (-not (Test-IsAdmin)) {
    Write-Err "Este script necesita permisos de administrador."
    Write-Host "    Clic derecho en setup-windows.bat -> Ejecutar como administrador"
    exit 1
}

Write-Host ""
Write-Host "AlejandrISBN — instalacion de prerequisitos (Windows)" -ForegroundColor White
Write-Host "Brave + Git + Docker Desktop via winget"
Write-Host ""

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Err "No se encuentra 'winget'."
    Write-Host "    Actualiza Windows o instala 'App Installer' desde Microsoft Store:"
    Write-Host "    https://apps.microsoft.com/detail/9nblggh4nns1"
    exit 1
}

Write-Step "Actualizando catalogo winget"
try {
    & winget source update --disable-interactivity 2>$null | Out-Null
} catch {
    Write-Warn "No se pudo actualizar el catalogo; se continua igual."
}

# --- Installs ----------------------------------------------------------------

$results = [ordered]@{
    "Brave Browser"  = Install-WingetPackage -Id "Brave.Brave" -DisplayName "Brave Browser"
    "Git"            = Install-WingetPackage -Id "Git.Git" -DisplayName "Git"
    "Docker Desktop" = Install-WingetPackage -Id "Docker.DockerDesktop" -DisplayName "Docker Desktop"
}

# Refresh PATH for this session (Git / Docker often land after install)
$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($machinePath -and $userPath) {
    $env:Path = "$machinePath;$userPath"
} elseif ($machinePath) {
    $env:Path = $machinePath
}

Write-Step "Comprobaciones rapidas"
foreach ($cmd in @("git", "docker")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        Write-Ok "$cmd disponible en PATH"
    } else {
        Write-Warn "$cmd no esta en PATH todavia (normal hasta reiniciar o abrir una terminal nueva)"
    }
}

# --- Summary -----------------------------------------------------------------

Write-Host ""
Write-Host "Resumen" -ForegroundColor White
foreach ($name in $results.Keys) {
    if ($results[$name]) {
        Write-Host "  [OK] $name" -ForegroundColor Green
    } else {
        Write-Host "  [FALLO] $name" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Siguientes pasos" -ForegroundColor White
Write-Host "  1. Si Docker Desktop lo pide, reinicia el PC."
Write-Host "  2. Abre Docker Desktop y espera a que este en marcha (icono de ballena)."
Write-Host "  3. Si aun no tienes el repo:"
Write-Host "       git clone https://github.com/pabloqpacin/AlejandrISBN.git"
Write-Host "  4. Entra en la carpeta AlejandrISBN y ejecuta start.bat"
Write-Host "  5. Abre http://localhost:8000 en Brave (u otro navegador)."
Write-Host ""
Write-Host "Guia completa: docs\SELFHOSTING.md"
Write-Host ""

$failed = @($results.Values | Where-Object { -not $_ }).Count
if ($failed -gt 0) {
    Write-Warn "Hubo $failed instalacion(es) fallida(s). Revisa los mensajes de arriba."
    exit 1
}

Write-Ok "Prerequisitos instalados."
exit 0
