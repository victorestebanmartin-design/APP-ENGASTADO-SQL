/*
 * panel_produccion.ino
 * Panel de órdenes para 4D Systems gen4-ESP32-24 (240×320, ILI9341)
 *
 * Librerías necesarias (Gestor de librerías del Arduino IDE):
 *   - TFT_eSPI       por Bodmer
 *   - ArduinoJson    por Benoît Blanchon (v7.x)
 *
 * ⚠ PINES: edita User_Setup.h (en la carpeta de esta sketch) y cópialo
 *   a <Arduino>/libraries/TFT_eSPI/ antes de compilar.
 *   Consulta el datasheet 4D Systems gen4-ESP32-24 para confirmar los pines.
 *
 * Protocolo serial (viene del PC via bridge_esp32.py):
 *   {"p":12,"e":5,"t":47,"hora":"10:45","fecha":"07/08"}\n
 *   p = pendientes, e = en_proceso, t = terminadas
 *
 * Baudios: 115200
 */

#include <TFT_eSPI.h>
#include <ArduinoJson.h>

// ── Colores (RGB565) ──────────────────────────────────────────────────────────
#define C_FONDO       0x0000   // negro
#define C_TITULO      0xFFFF   // blanco
#define C_SUBTITULO   0x8410   // gris claro
#define C_PENDIENTE   0xFFE0   // amarillo
#define C_EN_PROCESO  0xFD20   // naranja
#define C_TERMINADA   0x07E0   // verde
#define C_SEPARADOR   0x4208   // gris oscuro
#define C_SIN_DATOS   0xF800   // rojo (sin conexión)
// ─────────────────────────────────────────────────────────────────────────────

TFT_eSPI tft = TFT_eSPI();

// Estado actual
int  val_pendiente  = -1;
int  val_en_proceso = -1;
int  val_terminada  = -1;
char str_hora[6]    = "--:--";
char str_fecha[6]   = "--/--";
bool conectado      = false;
unsigned long ultimo_rx = 0;
unsigned long ultima_actualizacion_reloj = 0;

// ── Posiciones en pantalla (portrait 240×320) ─────────────────────────────────
#define Y_TITULO        6
#define Y_DATETIME     38
#define Y_SEP1         58
#define Y_FILA1        75
#define Y_FILA2       135
#define Y_FILA3       195
#define Y_SEP2        252
#define Y_ESTADO      265
// ─────────────────────────────────────────────────────────────────────────────

void dibujar_pantalla_completa() {
    tft.fillScreen(C_FONDO);

    // Título
    tft.setTextColor(C_TITULO, C_FONDO);
    tft.setTextSize(2);
    tft.setCursor(10, Y_TITULO);
    tft.print("ENGASTADO");

    // Separador superior
    tft.drawFastHLine(0, Y_SEP1, 240, C_SEPARADOR);
    // Separador inferior
    tft.drawFastHLine(0, Y_SEP2, 240, C_SEPARADOR);

    // Etiquetas (izquierda, pequeñas)
    tft.setTextSize(2);
    tft.setTextColor(C_PENDIENTE, C_FONDO);
    tft.setCursor(10, Y_FILA1 + 8);
    tft.print("PENDIENTES");

    tft.setTextColor(C_EN_PROCESO, C_FONDO);
    tft.setCursor(10, Y_FILA2 + 8);
    tft.print("EN PROCESO");

    tft.setTextColor(C_TERMINADA, C_FONDO);
    tft.setCursor(10, Y_FILA3 + 8);
    tft.print("TERMINADAS");
}

void dibujar_numero(int y, uint16_t color, int valor) {
    // Borra zona del número (derecha, 80px)
    tft.fillRect(155, y, 80, 40, C_FONDO);
    tft.setTextColor(color, C_FONDO);
    tft.setTextSize(3);

    if (valor < 0) {
        tft.setCursor(175, y + 4);
        tft.print("--");
    } else {
        // Alinear a la derecha en 3 dígitos
        int x_offset = (valor < 10) ? 195 : (valor < 100) ? 175 : 155;
        tft.setCursor(x_offset, y + 4);
        tft.print(valor);
    }
}

void dibujar_datetime() {
    tft.setTextSize(1);
    tft.setTextColor(C_SUBTITULO, C_FONDO);
    tft.fillRect(0, Y_DATETIME, 240, 18, C_FONDO);
    tft.setCursor(10, Y_DATETIME);
    tft.print(str_fecha);
    tft.print("  ");
    tft.print(str_hora);
}

void dibujar_estado(bool ok) {
    tft.fillRect(0, Y_ESTADO, 240, 20, C_FONDO);
    tft.setTextSize(1);
    if (ok) {
        tft.setTextColor(C_TERMINADA, C_FONDO);
        tft.setCursor(10, Y_ESTADO);
        tft.print("Conectado  Actualizacion: ");
        tft.print(str_hora);
    } else {
        tft.setTextColor(C_SIN_DATOS, C_FONDO);
        tft.setCursor(10, Y_ESTADO);
        tft.print("Sin datos del PC...");
    }
}

void procesar_json(const String& linea) {
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, linea);
    if (err) return;

    int np = doc["p"] | -1;
    int ne = doc["e"] | -1;
    int nt = doc["t"] | -1;
    const char* hora  = doc["hora"]  | "--:--";
    const char* fecha = doc["fecha"] | "--/--";

    strncpy(str_hora,  hora,  5);  str_hora[5]  = '\0';
    strncpy(str_fecha, fecha, 5);  str_fecha[5] = '\0';

    // Solo redibujar si cambió el valor
    if (np != val_pendiente)  { val_pendiente  = np; dibujar_numero(Y_FILA1, C_PENDIENTE,   val_pendiente);  }
    if (ne != val_en_proceso) { val_en_proceso = ne; dibujar_numero(Y_FILA2, C_EN_PROCESO,  val_en_proceso); }
    if (nt != val_terminada)  { val_terminada  = nt; dibujar_numero(Y_FILA3, C_TERMINADA,   val_terminada);  }

    dibujar_datetime();
    conectado = true;
    ultimo_rx = millis();
    dibujar_estado(true);
}

void setup() {
    Serial.begin(115200);
    tft.init();
    tft.setRotation(0);   // portrait, conector abajo
    dibujar_pantalla_completa();
    dibujar_numero(Y_FILA1, C_PENDIENTE,  -1);
    dibujar_numero(Y_FILA2, C_EN_PROCESO, -1);
    dibujar_numero(Y_FILA3, C_TERMINADA,  -1);
    dibujar_datetime();
    dibujar_estado(false);
}

void loop() {
    // Leer líneas completas del serial
    if (Serial.available()) {
        String linea = Serial.readStringUntil('\n');
        linea.trim();
        if (linea.startsWith("{")) {
            procesar_json(linea);
        }
    }

    // Marcar como desconectado si no hay datos en >90 s
    if (conectado && (millis() - ultimo_rx > 90000UL)) {
        conectado = false;
        dibujar_estado(false);
    }
}
