<#
.SYNOPSIS
    Deja un PC de puesto listo para COJOsw: quita el "No es seguro" del
    navegador y crea el acceso directo que abre la app sin barra de direcciones.

.DESCRIPCION
    El aviso "No es seguro" no lo pone la app: lo pone el navegador porque se
    entra por http:// en vez de https://. Los navegadores marcan asi TODO
    origen que no sea https, con la unica excepcion de localhost -- da igual
    que la red este aislada y sin internet.

    Montar https de verdad aqui pediria un certificado y meterlo en el almacen
    de confianza de cada PC, para no ganar nada: en una red de planta cerrada
    no hay nadie en medio de quien protegerse. Lo que se hace en su lugar es
    decirle al navegador, por politica de empresa, que ESE origen concreto es
    de fiar.

    Eso arregla dos cosas de una vez:
      1. Desaparece el "No es seguro".
      2. El origen pasa a ser "contexto seguro", que es lo que exige el
         navegador para registrar el service worker. Es decir: vuelve a
         ofrecer "Instalar aplicacion" (ver templates/_head_pwa.html).

.EXAMPLE
    # Como administrador, en el PC del puesto:
    powershell -ExecutionPolicy Bypass -File .\configurar_pc_puesto.ps1

.EXAMPLE
    # Si el servidor esta en otra IP o puerto:
    .\configurar_pc_puesto.ps1 -Origen "http://192.168.50.1:5001"

.NOTES
    Hay que ejecutarlo como administrador: escribe en HKLM (politicas del
    equipo, no del usuario), asi vale para cualquiera que se logue en ese PC.
    Despues hay que cerrar del todo el navegador y volver a abrirlo.
#>

[CmdletBinding()]
param(
    # Origen exacto de la app: esquema + host + puerto, sin barra final.
    # Tiene que coincidir LETRA POR LETRA con lo que se escribe en el
    # navegador: si entras por IP, aqui va la IP (no el nombre del equipo).
    [string]$Origen = "http://192.168.50.1:5001",

    # No crear el acceso directo, solo aplicar la politica.
    [switch]$SinAccesoDirecto,

    # Nombre del acceso directo en el escritorio.
    [string]$NombreAcceso = "COJOsw"
)

$ErrorActionPreference = 'Stop'

function Test-Administrador {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrador)) {
    Write-Error "Ejecuta este script como administrador (boton derecho -> Ejecutar como administrador)."
    exit 1
}

if ($Origen -notmatch '^https?://[^/]+$') {
    Write-Error "El origen debe ser como 'http://192.168.50.1:5001' (sin ruta ni barra final). Recibido: '$Origen'"
    exit 1
}

Write-Host ""
Write-Host "=== Configurando este PC para COJOsw ===" -ForegroundColor Cyan
Write-Host "Origen de confianza: $Origen"
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Politica: tratar ese origen como seguro
# ---------------------------------------------------------------------------
# OverrideSecurityRestrictionsOnInsecureOrigin es una politica de empresa de
# Chrome/Edge. Es una LISTA, asi que se guarda como valores numerados ("1",
# "2"...) dentro de una clave con el nombre de la politica.
$navegadores = @(
    @{ Nombre = 'Google Chrome';  Clave = 'HKLM:\SOFTWARE\Policies\Google\Chrome' },
    @{ Nombre = 'Microsoft Edge'; Clave = 'HKLM:\SOFTWARE\Policies\Microsoft\Edge' }
)

foreach ($nav in $navegadores) {
    $claveLista = Join-Path $nav.Clave 'OverrideSecurityRestrictionsOnInsecureOrigin'
    try {
        if (-not (Test-Path $claveLista)) {
            New-Item -Path $claveLista -Force | Out-Null
        }

        # Si ya estaba, no duplicarlo: se reescribe la lista entera con el
        # origen al frente y lo que hubiera detras.
        $existentes = @()
        (Get-Item $claveLista).GetValueNames() | Sort-Object | ForEach-Object {
            $v = (Get-ItemProperty -Path $claveLista -Name $_).$_
            if ($v -and $v -ne $Origen) { $existentes += $v }
        }
        (Get-Item $claveLista).GetValueNames() | ForEach-Object {
            Remove-ItemProperty -Path $claveLista -Name $_ -ErrorAction SilentlyContinue
        }

        $i = 1
        foreach ($valor in (@($Origen) + $existentes)) {
            New-ItemProperty -Path $claveLista -Name "$i" -Value $valor -PropertyType String -Force | Out-Null
            $i++
        }
        Write-Host ("  [OK] {0}: origen marcado como de confianza" -f $nav.Nombre) -ForegroundColor Green
    }
    catch {
        Write-Host ("  [--] {0}: no se pudo aplicar ({1})" -f $nav.Nombre, $_.Exception.Message) -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# 2. Acceso directo en modo aplicacion (sin barra de direcciones)
# ---------------------------------------------------------------------------
# --app abre la web como si fuera un programa: sin barra de direcciones, sin
# pestañas y sin botones de navegacion. En un puesto es lo que se quiere --
# el operario no tiene que ver ninguna URL, ni poder irse a otro sitio.
if (-not $SinAccesoDirecto) {
    $rutasNavegador = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
    )
    $exe = $rutasNavegador | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $exe) {
        Write-Host "  [--] No se encontro Chrome ni Edge: sin acceso directo." -ForegroundColor Yellow
    }
    else {
        $escritorio = [Environment]::GetFolderPath('CommonDesktopDirectory')
        $lnk = Join-Path $escritorio "$NombreAcceso.lnk"
        $shell = New-Object -ComObject WScript.Shell
        $acceso = $shell.CreateShortcut($lnk)
        $acceso.TargetPath = $exe
        $acceso.Arguments = "--app=$Origen"
        $acceso.Description = "COJOsw - Sistema de Engastado"
        $acceso.Save()
        Write-Host ("  [OK] Acceso directo creado: {0}" -f $lnk) -ForegroundColor Green
        Write-Host ("       ({0} --app=...)" -f (Split-Path $exe -Leaf)) -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Listo. Cierra el navegador DEL TODO (todas las ventanas) y vuelve a abrirlo." -ForegroundColor Cyan
Write-Host "Para comprobar que la politica esta puesta: chrome://policy" -ForegroundColor DarkGray
Write-Host ""
