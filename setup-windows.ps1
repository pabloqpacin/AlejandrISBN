#Requires -Version 5.1
<#
.SYNOPSIS
  Instala prerequisitos de AlejandrISBN en Windows: Brave, Git y Docker Desktop.

.DESCRIPTION
  Usa winget (Windows 10/11). Requiere administrador.
  Lanzalo con setup-windows.bat (doble clic) o:
    powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1

.NOTES
  Tras Docker Desktop suele hacer falta reiniciar y abrir Docker Desktop
  antes de usar start.bat.
#>

$ErrorActionPreference = "Continue"

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
    # 0 = ok
    # -1978335189 = already installed
    # -1978335212 = no applicable upgrade / no newer package
    return ($Code -eq 0) -or ($Code -eq -1978335189) -or ($Code -eq -1978335212)
}

function Install-WingetPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$DisplayName
    )

    Write-Step "Instalando $DisplayName ($Id)"

    $wingetArgs = @(
        "install", "-e", "--id", $Id,
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity"
    )

    & winget @wingetArgs
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }

    if (Test-WingetSuccess ([int]$code)) {
        Write-Ok "$DisplayName listo (codigo winget: $code)"
        return $true
    }

    Write-Err "Fallo al instalar $DisplayName (codigo winget: $code)"
    Write-Host "    Prueba manual en PowerShell (admin):" -ForegroundColor Yellow
    Write-Host "      winget install -e --id $Id --accept-package-agreements --accept-source-agreements"
    return $false
}

# --- Self-elevate -------------------------------------------------------------

if (-not (Test-IsAdmin)) {
    Write-Warn "Sin permisos de administrador. Relanzando con UAC..."
    $scriptPath = $MyInvocation.MyCommand.Path
    try {
        Start-Process -FilePath "powershell.exe" `
            -Verb RunAs `
            -WorkingDirectory (Split-Path -Parent $scriptPath) `
            -ArgumentList @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", "`"$scriptPath`""
            ) | Out-Null
        exit 0
    } catch {
        Write-Err "No se pudo elevar. Clic derecho en setup-windows.bat -> Ejecutar como administrador."
        Write-Host "    Detalle: $($_.Exception.Message)"
        if ($Host.Name -eq "ConsoleHost") { Read-Host "Pulsa Enter para salir" }
        exit 1
    }
}

try {
    Get-ChildItem -LiteralPath $PSScriptRoot -Filter "setup-windows.*" -ErrorAction SilentlyContinue |
        Unblock-File -ErrorAction SilentlyContinue
} catch {}

# --- Banner ------------------------------------------------------------------

Write-Host ""
Write-Host "AlejandrISBN - instalacion de prerequisitos (Windows)" -ForegroundColor White
Write-Host "Brave + Git + Docker Desktop via winget"
Write-Host "Carpeta: $PSScriptRoot"
Write-Host ""

# --- winget ------------------------------------------------------------------

$wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
if (-not $wingetCmd) {
    $wingetCandidates = @(
        "$env:LocalAppData\Microsoft\WindowsApps\winget.exe",
        "$env:ProgramFiles\WindowsApps\Microsoft.DesktopAppInstaller_*_*__8wekyb3d8bbwe\winget.exe"
    )
    foreach ($candidate in $wingetCandidates) {
        $resolved = Get-Item $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($resolved) {
            $env:Path = "$(Split-Path $resolved.FullName);$env:Path"
            $wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
            if ($wingetCmd) { break }
        }
    }
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Err "No se encuentra 'winget'."
    Write-Host "    1) Abre Microsoft Store"
    Write-Host "    2) Instala o actualiza 'Instalador de aplicacion' (App Installer)"
    Write-Host "    3) O abre: https://aka.ms/getwinget"
    Write-Host "    4) Cierra esta ventana, abre otra y vuelve a ejecutar setup-windows.bat"
    if ($Host.Name -eq "ConsoleHost") { Read-Host "Pulsa Enter para salir" }
    exit 1
}

Write-Ok "winget encontrado: $((Get-Command winget).Source)"

Write-Step "Actualizando catalogo winget"
& winget source update --disable-interactivity
if (-not (Test-WingetSuccess ([int]$LASTEXITCODE))) {
    Write-Warn "No se pudo actualizar el catalogo; se continua igual."
}

# --- Installs ----------------------------------------------------------------

$results = [ordered]@{
    "Brave Browser"  = Install-WingetPackage -Id "Brave.Brave" -DisplayName "Brave Browser"
    "Git"            = Install-WingetPackage -Id "Git.Git" -DisplayName "Git"
    "Docker Desktop" = Install-WingetPackage -Id "Docker.DockerDesktop" -DisplayName "Docker Desktop"
}

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
    Write-Host ""
    Write-Host "Plan B (PowerShell como administrador), una a una:" -ForegroundColor Yellow
    Write-Host "  winget install -e --id Brave.Brave --accept-package-agreements --accept-source-agreements"
    Write-Host "  winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements"
    Write-Host "  winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements"
    if ($Host.Name -eq "ConsoleHost") { Read-Host "Pulsa Enter para salir" }
    exit 1
}

Write-Ok "Prerequisitos instalados."
if ($Host.Name -eq "ConsoleHost") { Read-Host "Pulsa Enter para salir" }
exit 0
