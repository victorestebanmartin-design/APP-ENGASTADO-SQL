# Firmware diagnostico ESP32-P4-101CT-CLB

Primera prueba de la pantalla grande 4D Systems ESP32-P4 MIPI.

## Hardware confirmado

- Placa: 4D Systems ESP32-P4 MIPI / ESP32-P4-101CT-CLB.
- Panel: 800 x 1280, orientacion vertical.
- LCD: JD9365B, 2 lanes MIPI-DSI.
- Tactil: GT911.
- UART de datos: P4 GPIO52 RX y GPIO50 TX.
- Carro: GPIO45 TX -> P4 GPIO52 RX; carro GPIO46 RX <- P4 GPIO50 TX.
- Masa: P4 pin 3 o 4 a GND del carro.

## Herramientas

La libreria oficial de 4D Systems es `GFX4dESP32P4`, version probada por el
fabricante con Arduino-ESP32 Core 3.3.7:

https://github.com/4dsystems/GFX4dESP32P4

Instalar desde Arduino IDE o copiando la libreria en la carpeta `libraries`.
Seleccionar una placa ESP32-P4 compatible con Arduino-ESP32 3.3.7.

## Carga en COM10

1. Desconectar los tres cables UART del carro durante la primera carga.
2. Conectar la placa P4 por USB y comprobar que aparece como `COM10`.
3. Abrir `pantalla_p4_101.ino`.
4. Seleccionar la placa ESP32-P4 y el puerto COM10.
5. Compilar y cargar.
6. Abrir el monitor serie de UART0 a 115200.
7. Debe mostrar `P4 display diagnostic ready` y la pantalla `ESPERANDO CARRO`.

No usar el binario MicroPython del ESP32-S3 en esta placa P4.

## Prueba UART

Con la pantalla ya arrancada, conectar los tres cables con ambas placas
apagadas. Al recibir una instantanea del carro la pantalla debe mostrar
`DATOS RECIBIDOS`. El tactil imprime coordenadas en la consola UART0.

Este firmware es diagnostico. Todavia no confirma acciones ni dibuja los
paquetes completos; esas funciones se implementan despues de validar la
pantalla, el tactil y la comunicacion serie.
