# Pantalla grande ESP32-P4-101CT-CLB

## Placa identificada

La placa nueva es una **4D Systems ESP32-P4 MIPI** con cabecera macho de 30
posiciones. La cabecera expone GPIO de 3.3 V, dos entradas de 5 V y dos GND.
La pantalla y el tactil se conectan a sus conectores dedicados `DISPLAY` y
`TOUCH`; no se deben llevar esas señales por cables externos.

## Cabecera de 30 posiciones

| Pin | Señal | Uso en este proyecto |
|---:|---|---|
| 1, 2 | 5V IN | No conectar al carro; alimentar por USB-PWR |
| 3, 4 | GND | Masa común con el ESP32 del carro |
| 5 | GPIO52 | UART RX de la pantalla |
| 6 | ESP-EN | No conectar |
| 7 | GPIO50 | UART TX de la pantalla |
| 8 | GPIO51 | Libre |
| 9 | GPIO48 | Libre |
| 10 | GPIO49 | Libre |
| 11 | GPIO33 | Libre |
| 12 | GPIO47 | Libre |
| 13 | GPIO31 | Libre |
| 14 | GPIO32 | Libre |
| 15 | GPIO29 | Libre |
| 16 | GPIO30 | Libre |
| 17 | GPIO27 | Libre |
| 18 | GPIO28 | Libre |
| 19 | GPIO21 | Libre |
| 20 | GPIO26 | Libre |
| 21 | GPIO19 | Libre |
| 22 | GPIO20 | Libre |
| 23 | GPIO17 | Libre |
| 24 | GPIO18 | Libre |
| 25 | GPIO15 | Libre |
| 26 | GPIO16 | Libre |
| 27 | GPIO6 | Libre |
| 28 | GPIO14 | Libre |
| 29 | GPIO2 | Libre |
| 30 | GPIO3 | Libre |

Todos los GPIO de esta cabecera son exclusivamente de lógica de 3.3 V. No
aplicar 5 V a ninguno de ellos.

## Cableado UART inicial

| ESP32-S3 carro | ESP32-P4 pantalla | Función |
|---|---|---|
| GPIO45 (provisional TX) | GPIO52 (RX) | Estado carro hacia pantalla |
| GPIO46 (provisional RX) | GPIO50 (TX) | Eventos tactiles hacia carro |
| GND, pad 1/21/25/30 | GND, pin 3 o 4 | Referencia común |

La UART trabaja a 115200 baudios, 8 bits, sin paridad y un bit de parada.
El protocolo es JSON, una trama por línea (`\\n`).

## Alimentación

La placa P4 se alimenta por su entrada USB-PWR con 5 V. El carro conserva su
alimentación independiente. Solo se une la masa entre las dos placas; no se
unen los 5 V.

Antes de instalarla en el carro hay que medir el consumo de la pantalla con la
retroiluminación encendida. La fuente USB debe soportar como mínimo la
intensidad indicada por el fabricante de la placa y del panel.

## Secuencia de prueba

1. Programar y probar la P4 sin ningún cable UART conectado.
2. Con el carro apagado, conectar solo GND.
3. Conectar el TX del carro al RX de la P4 y comprobar que ambas placas arrancan.
4. Añadir el TX de la P4 al RX del carro solo cuando el primer sentido funcione.
5. Si el carro no arranca, retirar inmediatamente GPIO45/GPIO46 y probar otra
   asignación después de medir los niveles durante el reset.

GPIO45 y GPIO46 del ESP32-S3 del carro son pines de strapping. No deben quedar
forzados a nivel bajo durante el encendido. Esta asignación es provisional y
no se considera definitiva hasta completar la prueba de arranque con el cable
conectado.

## Programación de la P4

Mantener el USB de programación disponible y reservar UART0 para consola y
recuperación. El enlace de datos de producción usa otra UART, asignada a
GPIO52/GPIO50 mediante la matriz GPIO del ESP32-P4.
