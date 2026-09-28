# Busca una ventana de COJOsw ya abierta (PWA instalada o navegador en modo
# --app=) y la trae al frente. La llama abrir_app.bat antes de abrir una
# ventana nueva: sin esto, cada reinicio OTA (o cada pulsacion del icono con
# el servidor ya arrancado) abria otra ventana mas sin cerrar la anterior, y
# se iban acumulando.
#
# Sale con 0 si encontro una ventana y la enfoco (abrir_app.bat no abre otra).
# Sale con 1 si no hay ninguna (abrir_app.bat sigue con su logica normal).

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class VentanaCOJOsw {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);
}
"@

$ventana = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowHandle -ne [IntPtr]::Zero -and $_.MainWindowTitle -match 'COJOsw'
} | Select-Object -First 1

if (-not $ventana) {
    exit 1
}

if ([VentanaCOJOsw]::IsIconic($ventana.MainWindowHandle)) {
    [VentanaCOJOsw]::ShowWindowAsync($ventana.MainWindowHandle, 9) | Out-Null  # SW_RESTORE
}
[VentanaCOJOsw]::SetForegroundWindow($ventana.MainWindowHandle) | Out-Null
exit 0
