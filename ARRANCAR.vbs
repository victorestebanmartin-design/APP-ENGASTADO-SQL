' COJOsw: el icono de arranque. Es lo unico que hay que tocar para usar la app
' en el PC servidor.
'
'   - Si el servidor NO esta en marcha: lo arranca SIN ventana de consola,
'     espera a que este listo y abre la app.
'   - Si YA esta en marcha: no arranca un segundo servidor, solo abre la app.
'
' Asi se puede pulsar el icono las veces que haga falta: nunca duplica
' servidores y siempre acaba con la app delante.
'
' Este script es corto a proposito y NO comprueba nada por su cuenta: la
' directiva de IT de los PCs de la empresa bloquea los scripts de Windows que
' hacen una peticion HTTP y ademas lanzan un proceso (patron de dropper), asi
' que de decidir si hay servidor y de esperar a que este listo se encarga
' arranque_local.py. Aqui solo se lanza run.bat sin ventana.
'
' Se usa VBScript y no PowerShell porque WScript.Shell.Run con intWindowStyle
' = 0 no ensena ni un parpadeo de ventana, no depende de la politica de
' ejecucion de scripts y no pide permisos de administrador.
'
' Para DEPURAR, usa run.bat: ahi ves la consola y los errores en vivo.
' Para pararlo: Admin -> Sistema -> Apagar servidor (o detener.bat).

Option Explicit

Dim shell, fso, carpeta

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = carpeta

' 0 = ventana oculta. False = no esperar: el servidor se queda corriendo.
shell.Run "cmd /c """"" & carpeta & "\run.bat"" SILENCIOSO""", 0, False
