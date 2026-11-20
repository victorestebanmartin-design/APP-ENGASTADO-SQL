# Historial de cambios

Lo que ve el operario al pulsar la version de la esquina de cada pantalla.
Una entrada por version, la mas nueva arriba, en palabras de planta: que
cambia para quien usa la app, no como esta hecho por dentro.

Formato: `## X.Y.Z - AAAA-MM-DD` y debajo una linea `- ` por cambio.

## 1.44.1 - 2026-11-20
- Pick-to-light separa las pruebas de los «Ajustes del puesto», que sí se guardan y los usa el pick-to-light de verdad. El título ya no dice «Modo Prueba»
- «Restaurar» una copia sale en rojo: sustituye la base de datos entera
- Títulos de Admin más claros y sin iconos repetidos (por ejemplo «Exigir tarjeta en toda la app» o «Actualizar la app»)

## 1.44.0 - 2026-11-20
- Admin → Operarios es ahora una lista en tabla: Nº, nombre, tarjeta y una columna por cada permiso con su casilla. Se ve de un vistazo quién puede entrar a qué
- Los permisos se guardan solos al marcar o desmarcar la casilla (la celda parpadea en verde), sin botón «Guardar permisos». Dar Administración pide confirmación
- Buscador encima de la tabla, por nombre, número o tarjeta. Los operarios desactivados salen atenuados
- Arreglado: a un operario al que nunca se le habían tocado los permisos, la pantalla le marcaba «Calidad» y «Supervisor de ensayos» aunque en realidad no los tenía

## 1.43.8 - 2026-11-20
- El menú de Admin es ahora un árbol: «Planta», «Placas y hardware», «Propuestas y calidad» y «Sistema» son cabeceras con flecha ▸ que se despliegan al pulsarlas. Solo queda abierto el grupo en el que estás, así que el menú cabe sin tener que bajar
- Las propuestas salen como «Mangueras» y «Engastado» con el número de pendientes en una pastilla ámbar. Con el grupo plegado, un punto ámbar en la cabecera avisa de que hay alguna pendiente

## 1.43.7 - 2026-11-20
- Admin abre más rápido: cada apartado carga sus datos al pulsarlo, no todos a la vez al entrar. Al entrar ya no se buscan placas en los puertos USB del servidor (antes lo hacía cuatro veces aunque no fueras a grabar nada)

## 1.43.6 - 2026-11-20
- Nueva entrada en Admin, «Preparar placa nueva»: para una placa recién sacada de la caja. Arriba los drivers USB (si Windows no le da puerto COM) y debajo grabarle MicroPython. Antes estaba mezclado con el diagnóstico y había que ir y volver entre pantallas
- «Grabar pantalla grande (P4)» pasa a Pantallas de carro, debajo de «Subir firmware por USB»: todo lo de grabar pantallas queda junto
- «Diagnóstico» se queda solo con el chequeo en vivo y pasa a llamarse «Diagnóstico en vivo»
- El botón «Borrar y grabar MicroPython» sale en rojo: borra la placa entera

## 1.43.5 - 2026-11-20
- «Sistema» de Admin se parte en tres, porque tenía diez cosas mezcladas: «Este PC» (el PIN y la caché del puesto de este ordenador), «Servidor» (actualizar, exigir tarjeta, quitar el aviso «No es seguro», instalar en otro PC y, al final, reiniciar o apagar) y «Datos y copias» (copia automática, exportar y, al final, importar)
- «Quitar el aviso No es seguro» pasa de Red e IPs a Servidor: va de los PCs de puesto, no de las placas
- El botón «Importar y reemplazar BD» sale en rojo como botón peligroso, y las copias bajadas de PythonAnywhere ya no se confunden de nombre con la copia automática

## 1.43.4 - 2026-11-20
- Liberar paquetes bloqueados se hace ahora en Admin → Operarios, justo debajo de liberar logins colgados: los dos arreglan lo mismo, un puesto que se quedó a medias. Antes estaba en Sistema
- En Admin → Red e IPs sale arriba la tabla de placas y PCs con su IP, que es lo que más se consulta. La WiFi y la explicación de la red van debajo
- Al grabar una placa por USB, la opción de laboratorio se llama igual en pantallas y en lectores: «Laboratorio: WiFi con Internet + PythonAnywhere»

## 1.43.3 - 2026-11-20
- El menú de Admin se ordena en grupos: «Planta» (archivos, puestos, operarios, cables), «Placas y hardware» (pantallas, lectores, pick-to-light, red, diagnóstico), «Revisión» y «Sistema»
- Nombres más claros: «Display Carro» pasa a «Pantallas de carro», «Red y placas» a «Red e IPs» (y así se llama también en los avisos que mandan allí) y «Cable» a «Cables»

## 1.43.2 - 2026-11-20
- Admin, arriba: se ve claro con qué has entrado. Con tu cuenta sale «👤 tu nombre»; con el PIN sale en ámbar «🔑 Entrada con PIN (sin nombre)», y al pasar el ratón explica que así no se pueden aprobar propuestas
- Menú de Admin más corto: «Organización» y «Report» ya no son pantallas que solo mandaban a otro sitio, ahora son enlaces directos («Puestos y máquinas ↗» y «Calidad (report) ↗»)
- Las propuestas de mangueras y de engastado llevan icono en el menú, y Sistema tiene el suyo (⚙️), distinto del de los botones de actualizar

## 1.43.1 - 2026-11-20
- Admin abre sin errores por detrás: ya no intenta cargar una lista de puestos que se había ido a «Puestos y máquinas»
- La tarjeta «Quitar el aviso No es seguro» (Admin → Red y placas) ya se ve como las demás, con su fondo y su borde

## 1.43.0 - 2026-11-20
- Admin → «Color de Cable» pasa a llamarse «Cable» y tiene una columna nueva, «Corte manual»: se marca con un tick en los cables que se cortan a mano. Se puede marcar aunque el cable no tenga color
- Al preparar una manguera de un cable marcado como corte manual sale un aviso grande «⚠️ CORTE MANUAL · revisa la longitud de la manguera» y la longitud se ve resaltada. El aviso sale al abrir el corte: si ya estaba abierto, vuelve a escanear la orden

## 1.42.0 - 2026-11-20
- Los puestos de engastado pueden convertirse en un puesto de manguitos y mangueras: en la pantalla de «Pasa tu tarjeta», el botón ⇄ de abajo a la derecha (se pulsa dos veces para confirmar). Desde ese momento, quien pase la tarjeta por el lector de ese puesto entra en manguitos y mangueras. Se queda así hasta que alguien lo vuelva a cambiar con el mismo botón
- Arriba se ve en qué modo está el puesto (por ejemplo «MECATRACTION · Manguitos y Mangueras»). No se puede cambiar mientras alguien tenga la sesión abierta en ese puesto

## 1.41.0 - 2026-11-20
- La pantalla grande del carro (10,1") ya se graba desde Admin → Diagnóstico ESP32, como las pequeñas: se enchufa por USB al PC de fábrica, se elige el puerto y se pulsa «Compilar y grabar». La primera vez tarda unos 12 minutos; después, menos de un minuto

## 1.40.1 - 2026-11-19
- Con dos PCs de mangueras y manguitos, cada lector RFID se puede asignar a su PC (Admin → Lectores RFID, opciones 💻 con la IP). Así, pasar la tarjeta abre solo la pantalla de ese PC y no las dos a la vez con el mismo operario
- En Admin → Lectores RFID, cada opción del desplegable dice la IP del PC al que llega y el nombre que le pusiste en Admin → IPs, para saber qué pantalla se abrirá sin ir a mirarlo

## 1.40.0 - 2026-11-18
- Admin → Sistema tiene un botón «Reiniciar servidor»: apaga la app y la vuelve a arrancar sola, sin tener que ir al PC servidor. Los puestos se quedan sin ella unos segundos

## 1.39.0 - 2026-11-18
- La pantalla de un carro vacío enseña su código QR al pulsar OK: se escanea con la pistola al generar un bono. Se cierra sola a los 10 segundos o con otro OK

## 1.38.2 - 2026-11-18
- En preparacion de mangueras se ve ahora la longitud de la manguera, en pequeño junto al contador

## 1.38.1 - 2026-11-18
- Calidad tiene ahora el mismo aspecto oscuro que Administracion, y se leen bien los titulos de las tablas, que antes salian blanco sobre gris claro

## 1.38.0 - 2026-11-17
- Admin → Sistema tiene una tarjeta nueva, "Copia automatica": cuando fue la ultima copia, si ha salido bien y un boton para hacer una copia en el momento
- Las copias automaticas se pueden hacer ademas en un disco externo: se indica su carpeta en esa tarjeta. Si el disco no esta enchufado se avisa, y el servidor sigue copiando igual
- Cada copia se comprueba al hacerla, y ahora incluye tambien los documentos de las maquinas y los datos de manguitos

## 1.37.1 - 2026-11-17
- Propuestas de mangueras: la tabla ya no se sale por la derecha. El nombre del corte se parte en varias lineas, las medidas no se cortan a mitad y los botones van uno encima de otro

## 1.37.0 - 2026-11-17
- Propuestas de mangueras con el mismo aspecto que las de engastado: pestanas por estado, buscador y encabezados fijos al bajar
- Aceptar o rechazar propuestas de mangueras es de un clic: el comentario ya es opcional, tambien al restaurar
- Se pueden marcar varias propuestas de mangueras y aceptarlas o rechazarlas de golpe

## 1.36.0 - 2026-11-17
- Propuestas de engastado con el aspecto de Admin: tabla con pestanas por estado, buscador y encabezados que no se pierden al bajar
- Aprobar o rechazar es de un clic: el comentario ya es opcional
- Se pueden marcar varias propuestas (clic en la fila, Mayus+clic para un tramo, o todas las que se ven) y aprobarlas o rechazarlas de golpe
- Al apagar el servidor ya no se queda abierta una ventana negra mas cada vez

## 1.35.3 - 2026-11-17
- Admin → Operarios: el boton de leer tarjeta vuelve a funcionar. Antes daba "_opBoton is not defined" y no dejaba asignar la tarjeta al operario

## 1.35.2 - 2026-11-17
- Al entrar eligiendo el nombre de la lista (sin tarjeta), solo valen operarios dados de alta y activos. Si alguno sale como "no esta dado de alta", hay que darlo de alta o reactivarlo en Admin → Operarios

## 1.35.1 - 2026-11-16
- El PIN de Administracion se guarda mejor protegido. No cambia nada al usarlo: el PIN de siempre sigue valiendo y se actualiza solo la primera vez que se introduce bien

## 1.35.0 - 2026-11-16
- Dar de alta, cambiar o dar de baja operarios y sus tarjetas solo se puede hacer desde Administracion, con el PIN o la clave personal
- Un PC solo se puede configurar como "Servidor" desde el propio PC servidor; desde otro equipo hay que entrar antes en Administracion
- El nombre de un operario ya no admite los simbolos < ni > y tiene un maximo de 60 caracteres
- Subir un Excel de corte ya no lo deja ocupado: revertir una propuesta justo despues ya no da error de vez en cuando

## 1.34.1 - 2026-11-16
- Aprobar o revertir una propuesta, aplicar el editor de mangueras o subir un Excel ya no dan error si el fichero esta ocupado un instante: se reintenta solo

## 1.34.0 - 2026-11-16
- Engastado: nuevo boton EMBALAJE, se enciende cuando hay alguna orden con todas sus maquinas acabadas
- La primera vez de cada codigo de corte se eligen las cajas y que paquetes van en cada una; la siguiente orden de esa referencia sale ya guiada
- Los carteles de las cajas salen en A4 horizontal, una hoja por caja, por la impresora de red antes de empezar a embalar: corte, denominacion, orden, cantidad y los paquetes de esa caja dibujados como sus etiquetas
- Cada paquete puede llevar una observacion (lo que hay que hacerle antes de meterlo en la caja): sale con * en la pantalla y en el cartel, y la pone o la cambia un supervisor
- Las cajas se pueden renombrar (por ejemplo "Conectores"); el cartel sigue diciendo CAJA 1 de 3 y debajo el nombre. Tambien con supervisor
- Embalar una orden con paquetes pendientes, o cambiar un reparto guardado, lo autoriza un supervisor con su tarjeta o su clave

## 1.33.2 - 2026-11-16
- Cambio interno: las comprobaciones automaticas de la app tardan cinco veces menos. Nada cambia en las pantallas

## 1.33.1 - 2026-11-12
- La pistola ya lee las etiquetas de orden aunque el guion salga como /M (mangueras, manguitos, generar bono y registro de ordenes)

## 1.33.0 - 2026-11-12
- Pulsando la version de la esquina de cualquier pantalla se ve que ha cambiado en cada version

## 1.32.1 - 2026-11-12
- Mangueras: las secciones AWG y +P tambien son mangueras

## 1.32.0 - 2026-11-11
- Propuestas de mangueras: aprobar una no caduca las demas, y restaurar

## 1.31.3 - 2026-11-11
- Ordenes duplicadas: limpieza prudente al arrancar

## 1.31.2 - 2026-11-10
- Copia automatica: solo se copian los Excel que han cambiado

## 1.31.1 - 2026-11-10
- Fiabilidad: progreso que se guarda de verdad, bloqueos que caducan y bonos sin sorpresas

## 1.31.0 - 2026-11-06
- Report de engastado: sin terminales descartados y operario con numero de empleado

## 1.30.1 - 2026-11-06
- Inspeccion de maquinas por mes: vale el mes entero de la etiqueta

## 1.30.0 - 2026-11-06
- Maquinas: la herramienta se pasa una vez y la inspeccion caducada bloquea

## 1.29.0 - 2026-11-05
- Maquinas: matricula, etiqueta RFID e inspeccion, y maquina en el report

## 1.28.0 - 2026-11-05
- Seccion IFA: terminales y retractil por corte para SAP

## 1.27.0 - 2026-11-05
- Tandas de paquetes segun la orden y carros sin tope de numeracion

## 1.26.0 - 2026-11-03
- Modulo Calidad: ensayos de traccion y report de trazabilidad juntos

## 1.25.2 - 2026-10-30
- El bloqueo de un paquete solo vale dentro de su misma orden

## 1.25.1 - 2026-10-30
- Imprimir etiquetas desde Mangueras y arreglo de colores de botones

## 1.25.0 - 2026-10-29
- Estado del carro en pantalla, vista del bono con QR y arreglos de etiquetas

## 1.24.0 - 2026-10-29
- Bonos montados por operarios, fases previas obligatorias y reentrada a ordenes terminadas

## 1.23.2 - 2026-10-27
- Muestra el n.º de paquete en propuestas y anade motivo IFA

## 1.22.2 - 2026-10-27
- Anade tiempo de manguitos, pagina de tiempos por orden y cierre por inactividad

## 1.21.3 - 2026-10-26
- Permite editar bonos con / en el nombre y bloquea / al crearlos

## 1.21.1 - 2026-10-16
- Evita falsas devoluciones PTL al fallar la lectura I2C

## 1.21.0 - 2026-10-16
- Permite avisar desde engastado de terminales que no se ponen

## 1.20.0 - 2026-10-15
- Permite planificar bonos y elegir carros por orden

## 1.19.1 - 2026-10-15
- Muestra cronometro acumulado en preparacion de mangueras

## 1.19.0 - 2026-10-14
- Registrar ordenes por escaneo y trazabilidad de preparacion de mangueras

## 1.18.1 - 2026-10-14
- Cierra el flujo de aprobación y rechazo de mangueras

## 1.18.0 - 2026-10-14
- Simplifica propuestas de mangueras y unifica acceso personal a Administración

## 1.17.0 - 2026-10-14
- Añade propuestas trazables de mangueras con aprobación personal

## 1.16.2 - 2026-10-14
- Ordena instrucciones de reetiquetado

## 1.16.1 - 2026-10-13
- Simplificar agrupacion de series por archivo

## 1.16.0 - 2026-10-13
- Permitir excluir cables de agrupacion por series

## 1.15.1 - 2026-10-13
- Añadir ayuda de origen, destino y longitud para identificar cables en engastado

## 1.15.0 - 2026-10-09
- Heredar preparaciones entre ediciones y aplicar sin descarga

## 1.14.5 - 2026-10-09
- Ocultar hijos asociados en preparacion de mangueras

## 1.14.4 - 2026-10-09
- Vincular activos KIT por observación y elemento RENFE

## 1.14.3 - 2026-10-09
- Aprender referencias MANG para hijos en corte RENFE

## 1.14.2 - 2026-10-09
- Quitar flechas de campos numéricos de mangueras

## 1.14.1 - 2026-10-09
- Mostrar observaciones y ordenar mangueras por paquete

## 1.14.0 - 2026-10-09
- Añadir biblioteca compartida de retractiles con medida por defecto

## 1.13.4 - 2026-10-09
- Añadir observaciones libres por manguera al Excel

## 1.13.3 - 2026-10-09
- Asociar activos de color y pantalla a manguera J de Zefiro

## 1.13.2 - 2026-10-09
- Asociar manguera L con activos L1, L2, L3 y pantalla

## 1.13.1 - 2026-10-09
- Reconocer activos entre paréntesis y unificar lados liso y guion

## 1.13.0 - 2026-10-09
- Identificar activos de mangueras y excluir lados sin pelado en engastado

## 1.12.0 - 2026-10-09
- Cerrar guardado de mangueras con descarga y aplicación al corte

## 1.11.1 - 2026-10-09
- Ajustar cabecera de mangueras para pantallas pequeñas

## 1.11.0 - 2026-10-09
- Añadir editor visual de preparación de mangueras con descarga Excel

## 1.10.0 - 2026-10-08
- Series en engastado sin cables ajenos; un terminal en una sola maquina; chip de maquinas en Puestos

## 1.9.0 - 2026-10-08
- Cambiar nº de orden en marcha y editar bonos (nombre/estado)

## 1.8.2 - 2026-10-07
- Terminales: asignar con maquinas eliminadas y ver los terminales de cada maquina

## 1.8.1 - 2026-10-07
- Devolucion PTL coherente al cambiar terminal o salir

## 1.8.0 - 2026-10-07
- Añade captura RFID dirigida por lector

## 1.7.0 - 2026-10-06
- Añadir puesto compartido de manguitos y mangueras con selección tras login

## 1.6.2 - 2026-10-06
- Vigilar herramientas PTL retiradas en reposo y durante engaste

## 1.6.1 - 2026-10-06
- Herramientas PTL: el modal de maquina no encendia la herramienta ni pedia RFID

## 1.6.0 - 2026-10-06
- Refactor pick-to-light functionality and enhance tool management

## 1.5.0 - 2026-10-05
- Manguitos por serie, reetiquetado de paquetes juntados y ref/ed sugeridas

## 1.4.0 - 2026-10-02
- Asignar herramienta manual desde catálogo, no texto libre

## 1.3.0 - 2026-10-01
- Identificación sin tarjeta en el gate de login

## 1.2.0 - 2026-09-29
- Trazabilidad RFID de herramientas manuales en el pick-to-light

## 1.1.0 - 2026-09-28
- Modo ahorro de la P4 conmutable desde el carro (botones 1+2, 5 s)

## 1.0.0 - 2026-09-25
- Version semantica visible en pantalla y COJOsw ya no se duplica al reiniciar
