' Crea en el Escritorio el acceso directo "COJOsw" que arranca la app, con el
' icono de COJOsw en vez del icono generico de VBScript.
'
' Un .vbs no puede llevar icono propio -- lo que se ve en el escritorio es
' siempre el icono de WScript -- pero un acceso directo (.lnk) A ese .vbs si
' puede llevar el que se le indique. Por eso este script no hace nada de la
' app: solo genera el .lnk una vez. Se ejecuta a mano cuando haga falta
' (primera instalacion, o si se borra el icono sin querer).
'
' IMPORTANTE: el nombre del .lnk NO puede empezar por "COJOsw". abrir_app.bat
' busca accesos directos "COJOsw*.lnk" en el Escritorio para detectar si la
' app esta instalada como PWA del navegador (eso da el icono en la barra de
' tareas) y la abre con `start`. Si este lanzador se llamara "COJOsw.lnk" se
' detectaria a si mismo como si fuera esa PWA y se re-lanzaria en bucle cada
' vez que el servidor arranca y quiere abrir la ventana.

Option Explicit

Dim shell, fso, carpeta, escritorio, enlace, acceso

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
escritorio = shell.SpecialFolders("Desktop")
enlace = escritorio & "\Arrancar COJOsw.lnk"

Set acceso = shell.CreateShortcut(enlace)
acceso.TargetPath = carpeta & "\ARRANCAR.vbs"
acceso.WorkingDirectory = carpeta
acceso.IconLocation = carpeta & "\static\img\cojosw.ico"
acceso.Description = "Abrir COJOsw - Sistema de Engastado Automatico"
acceso.Save

MsgBox "Icono creado en el Escritorio: COJOsw" & vbCrLf & vbCrLf & _
       "Doble clic ahi para arrancar la app.", vbInformation, "COJOsw"
