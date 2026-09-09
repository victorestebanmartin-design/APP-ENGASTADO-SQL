#include <Arduino.h>
#include "gfx4desp32_ESP32_P4_101CT_CLB.h"

// Cabecera P4: pin 5 = GPIO52 (RX), pin 7 = GPIO50 (TX).
static constexpr int UART_RX_PIN = 52;
static constexpr int UART_TX_PIN = 50;
static constexpr uint32_t UART_BAUD = 115200;
static constexpr uint16_t COLOR_GRAY = 0x8410;

// La libreria 4D reserva UART0 para programacion y consola.
gfx4desp32_ESP32_P4_101CT_CLB gfx;
HardwareSerial displayUart(1);
String linea;
unsigned long ultimoEstado = 0;

void dibujarEstado(const char *estado, uint16_t color) {
  gfx.Cls();
  gfx.Orientation(PORTRAIT);
  gfx.TextColor(WHITE, BLACK);
  gfx.Font(3);
  gfx.TextSize(1);
  gfx.MoveTo(35, 60);
  gfx.print("PANTALLA P4");
  gfx.TextColor(color, BLACK);
  gfx.MoveTo(35, 150);
  gfx.print(estado);
  gfx.TextColor(COLOR_GRAY, BLACK);
  gfx.MoveTo(35, 250);
  gfx.print("UART 115200 OK");
  gfx.MoveTo(35, 330);
  gfx.print("800 x 1280");
}

void procesarLinea(const String &mensaje) {
  if (mensaje.length() == 0) return;
  // En esta fase solo verificamos el enlace. El parser de paquetes vendra
  // despues de validar LCD, tactil y UART con el hardware real.
  if (mensaje.indexOf("\"tipo\":\"estado\"") >= 0) {
    dibujarEstado("DATOS RECIBIDOS", GREEN);
  } else {
    dibujarEstado("UART RECIBIDA", YELLOW);
  }
}

void setup() {
  Serial.begin(115200);
  gfx.begin();
  gfx.Cls();
  gfx.ScrollEnable(false);
  gfx.BacklightOn(true);
  gfx.Orientation(PORTRAIT);
  gfx.TextColor(WHITE, BLACK);
  gfx.Font(3);
  gfx.TextSize(1);
  gfx.touch_Set(TOUCH_ENABLE);

  displayUart.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
  dibujarEstado("ESPERANDO CARRO", ORANGE);
  Serial.println("P4 display diagnostic ready");
}

void loop() {
  while (displayUart.available()) {
    char c = static_cast<char>(displayUart.read());
    if (c == '\n') {
      procesarLinea(linea);
      linea = "";
    } else if (c != '\r' && linea.length() < 4096) {
      linea += c;
    } else if (linea.length() >= 4096) {
      linea = "";
    }
  }

  if (millis() - ultimoEstado > 30000) {
    ultimoEstado = millis();
    gfx.touch_Update();
    if (gfx.touch_GetPen() != NOTOUCH) {
      Serial.printf("TOUCH x=%d y=%d\n", gfx.touch_GetX(), gfx.touch_GetY());
    }
  }
}
