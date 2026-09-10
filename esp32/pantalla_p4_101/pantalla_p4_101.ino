/*
 * pantalla_p4_101.ino
 * Panel de producción para ESP32-P4 101CT CLB (portrait 800×1280)
 *
 * Recibe de main_wifi.py (carro) por UART1 rx=GPIO52 tx=GPIO50:
 *   {"v":1,"tipo":"estado","carro":"1","fw":"...","wifi":true,"ops":[
 *     {"operario":"key","data":{"puesto_nombre":"...","fase":"recoger|trabajando|devolver",
 *                               "paquetes":[...],...}},
 *     ...
 *   ]}
 *
 * Libreria necesaria: ArduinoJson >=7 (Gestor de librerias Arduino)
 */

#include <Arduino.h>
#include "gfx4desp32_ESP32_P4_101CT_CLB.h"
#include <ArduinoJson.h>

// ── UART del carro ────────────────────────────────────────────────────────────
static constexpr int          UART_RX_PIN = 52;
static constexpr int          UART_TX_PIN = 50;
static constexpr uint32_t     UART_BAUD   = 115200;

// ── Layout (portrait 800×1280) ────────────────────────────────────────────────
// Medidas empíricas: Font(3) TextSize(1) ocupa ~80 px de alto.
// Font(2) TextSize(1) ocupa ~50 px.
static constexpr int Y_CARRO   =   20;   // titulo grande
static constexpr int Y_INFO    =  110;   // wifi + fw
static constexpr int Y_OPS     =  200;   // inicio lista de ops
static constexpr int CARD_DY   =  190;   // alto por op (2 filas + margen)
static constexpr int Y_FOOTER  = 1210;   // linea de estado en pie
static constexpr int MAX_OPS   =    5;   // maximo visible (5×190=950 px, cabe)
static constexpr int X_IZQ     =   35;   // margen izquierdo

// ── Estado global ─────────────────────────────────────────────────────────────
struct Op {
    char puesto[48];
    char fase[16];
    int  npaq;
};

gfx4desp32_ESP32_P4_101CT_CLB gfx;
HardwareSerial                  carroUart(1);
String                          buf;

Op             ops_buf[MAX_OPS];
int            nops         = 0;
char           carro_id[8]  = "--";
char           fw_buf[28]   = "---";
bool           wifi_ok      = false;
unsigned long  ultimo_rx    = 0;
unsigned long  ultimo_hb    = 0;
bool           tiene_datos  = false;

// ── Helpers ───────────────────────────────────────────────────────────────────
static uint16_t colorFase(const char *f) {
    if (strcmp(f, "recoger")    == 0) return YELLOW;
    if (strcmp(f, "trabajando") == 0) return ORANGE;
    if (strcmp(f, "devolver")   == 0) return GREEN;
    return 0x8410; // gris
}
static const char *labelFase(const char *f) {
    if (strcmp(f, "recoger")    == 0) return "RECOGER";
    if (strcmp(f, "trabajando") == 0) return "EN PROCESO";
    if (strcmp(f, "devolver")   == 0) return "DEVOLVER";
    if (strcmp(f, "fin")        == 0) return "FINALIZADO";
    return f;
}

// ── Dibujo ────────────────────────────────────────────────────────────────────
static void dibujarPantalla() {
    gfx.Cls();
    gfx.Orientation(PORTRAIT);

    // ── Cabecera ──────────────────────────────────────────────────────────────
    gfx.Font(3); gfx.TextSize(1);
    gfx.TextColor(WHITE, BLACK);
    gfx.MoveTo(X_IZQ, Y_CARRO);
    gfx.print("CARRO ");
    gfx.print(carro_id);

    gfx.Font(2); gfx.TextSize(1);
    gfx.MoveTo(500, Y_CARRO + 15);
    if (wifi_ok) { gfx.TextColor(GREEN,  BLACK); gfx.print("WiFi OK"); }
    else         { gfx.TextColor(RED,    BLACK); gfx.print("Sin WiFi"); }

    gfx.TextColor(0x8410, BLACK); // gris
    gfx.MoveTo(X_IZQ, Y_INFO);
    gfx.print("fw: "); gfx.print(fw_buf);

    // ── Lista de puestos ──────────────────────────────────────────────────────
    int y = Y_OPS;
    if (nops == 0) {
        gfx.Font(3); gfx.TextSize(1);
        gfx.TextColor(0x8410, BLACK);
        gfx.MoveTo(X_IZQ, y);
        gfx.print("Sin puestos activos");
    } else {
        for (int i = 0; i < nops; i++) {
            // Nombre del puesto
            gfx.Font(3); gfx.TextSize(1);
            gfx.TextColor(WHITE, BLACK);
            gfx.MoveTo(X_IZQ, y);
            gfx.print(ops_buf[i].puesto[0] ? ops_buf[i].puesto : "(puesto)");

            // Numero de paquetes (derecha)
            gfx.Font(2); gfx.TextSize(1);
            gfx.TextColor(0x8410, BLACK);
            gfx.MoveTo(620, y + 10);
            gfx.print(ops_buf[i].npaq);
            gfx.print(" paq");

            // Fase (segunda fila, color segun estado)
            gfx.Font(3); gfx.TextSize(1);
            gfx.TextColor(colorFase(ops_buf[i].fase), BLACK);
            gfx.MoveTo(X_IZQ, y + 90);
            gfx.print(labelFase(ops_buf[i].fase));

            y += CARD_DY;
            if (y + 90 > Y_FOOTER) break; // no sobrepasar el footer
        }
    }

    // ── Pie de página ─────────────────────────────────────────────────────────
    gfx.Font(2); gfx.TextSize(1);
    gfx.MoveTo(X_IZQ, Y_FOOTER);
    if (tiene_datos) {
        gfx.TextColor(GREEN, BLACK);
        gfx.print("Conectado");
    } else {
        gfx.TextColor(RED, BLACK);
        gfx.print("Sin datos del carro...          ");
    }
}

// ── Parser JSON ───────────────────────────────────────────────────────────────
static void procesarLinea(const String &msg) {
    Serial.print("RX (");
    Serial.print(msg.length());
    Serial.print("): ");
    Serial.println(msg.substring(0, 100)); // no inundar serial

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, msg);
    if (err) {
        Serial.print("JSON err: "); Serial.println(err.c_str());
        return;
    }

    const char *tipo = doc["tipo"] | "";
    if (strcmp(tipo, "estado") != 0) return; // ignorar otros tipos

    // Extraer campos de cabecera
    strncpy(carro_id, doc["carro"] | "--", sizeof(carro_id) - 1);
    strncpy(fw_buf,   doc["fw"]    | "---", sizeof(fw_buf)  - 1);
    carro_id[sizeof(carro_id)-1] = '\0';
    fw_buf[sizeof(fw_buf)-1]     = '\0';
    wifi_ok = doc["wifi"] | false;

    // Extraer ops
    JsonArray arr = doc["ops"].as<JsonArray>();
    nops = 0;
    for (JsonObject op : arr) {
        if (nops >= MAX_OPS) break;
        JsonObject data = op["data"].as<JsonObject>();

        const char *pnom = data["puesto_nombre"] | "";
        const char *fase = data["fase"]          | "";
        strncpy(ops_buf[nops].puesto, pnom, sizeof(ops_buf[0].puesto) - 1);
        strncpy(ops_buf[nops].fase,   fase, sizeof(ops_buf[0].fase)   - 1);
        ops_buf[nops].puesto[sizeof(ops_buf[0].puesto)-1] = '\0';
        ops_buf[nops].fase[sizeof(ops_buf[0].fase)-1]     = '\0';

        JsonArray paq = data["paquetes"].as<JsonArray>();
        ops_buf[nops].npaq = (int)paq.size();
        nops++;
    }

    tiene_datos = true;
    ultimo_rx   = millis();
    dibujarPantalla();
}

// ── Setup / loop ──────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    gfx.begin();
    gfx.Cls();
    gfx.ScrollEnable(false);
    gfx.BacklightOn(true);
    gfx.Orientation(PORTRAIT);
    gfx.touch_Set(TOUCH_ENABLE);

    carroUart.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);

    // Pantalla de espera inicial (igual que el diagnóstico)
    gfx.TextColor(WHITE, BLACK);
    gfx.Font(3); gfx.TextSize(1);
    gfx.MoveTo(X_IZQ, Y_CARRO);  gfx.print("CARRO --");
    gfx.TextColor(ORANGE, BLACK);
    gfx.MoveTo(X_IZQ, Y_OPS);    gfx.print("ESPERANDO CARRO");
    gfx.TextColor(0x8410, BLACK);
    gfx.Font(2); gfx.TextSize(1);
    gfx.MoveTo(X_IZQ, Y_OPS+100); gfx.print("UART1 rx=52 tx=50  115200");

    Serial.println("P4 pantalla_p4_101 v2 ready");
    Serial.printf("UART1 rx=%d tx=%d baud=%u\n", UART_RX_PIN, UART_TX_PIN, UART_BAUD);
}

void loop() {
    // ── Lectura UART del carro ────────────────────────────────────────────────
    while (carroUart.available()) {
        char c = static_cast<char>(carroUart.read());
        if (c == '\n') {
            String s = buf; s.trim(); buf = "";
            if (s.length() > 0) procesarLinea(s);
        } else if (c != '\r' && buf.length() < 4096) {
            buf += c;
        } else if (buf.length() >= 4096) {
            Serial.println("RX overflow, descartado");
            buf = "";
        }
    }

    // ── Timeout: sin datos >90 s → pie en rojo ────────────────────────────────
    if (tiene_datos && millis() - ultimo_rx > 90000UL) {
        tiene_datos = false;
        gfx.Font(2); gfx.TextSize(1);
        gfx.TextColor(RED, BLACK);
        gfx.MoveTo(X_IZQ, Y_FOOTER);
        gfx.print("Sin datos del carro...          ");
    }

    // ── Heartbeat ─────────────────────────────────────────────────────────────
    if (millis() - ultimo_hb > 10000UL) {
        ultimo_hb = millis();
        Serial.printf("hb: nops=%d wifi=%d rx_age=%lums\n",
                      nops, (int)wifi_ok,
                      ultimo_rx ? millis() - ultimo_rx : 0UL);
        gfx.touch_Update();
        if (gfx.touch_GetPen() != NOTOUCH) {
            Serial.printf("TOUCH x=%d y=%d\n", gfx.touch_GetX(), gfx.touch_GetY());
        }
    }
}
