/*
 * pantalla_p4_101.ino
 * Panel de produccion para ESP32-P4 101CT CLB (portrait 800x1280)
 *
 * Recibe de main_wifi.py (carro) por UART1 rx=GPIO52 tx=GPIO50:
 *   {"v":1,"tipo":"estado","carro":"1","fw":"...","wifi":true,"ops":[
 *     {"operario":"key","data":{"puesto_nombre":"...","fase":"recoger|trabajando|devolver",
 *                               "lote":"...","paquetes":[...],...}},
 *     ...
 *   ]}
 *
 * Interfaz con la identidad del SW web (COJO): fondo claro, cabecera azul en
 * degradado, una tarjeta blanca por puesto con la fase en una pastilla de
 * color y el numero de paquetes. Solo pinta cuando el carro manda una
 * instantanea nueva; el pie refresca el "hace N s" cada segundo.
 *
 * Libreria necesaria: ArduinoJson >=7 (Gestor de librerias Arduino)
 */

#include <Arduino.h>
#include "gfx4desp32_ESP32_P4_101CT_CLB.h"
#include <ArduinoJson.h>

// ── UART del carro ───────────────────────────────────────────────────────────
static constexpr int      UART_RX_PIN = 52;
static constexpr int      UART_TX_PIN = 50;
static constexpr uint32_t UART_BAUD   = 115200;

// ── Paleta (RGB565), tomada del SW web ───────────────────────────────────────
// azul #2563eb / #1d4ed8, verde green-600, ambar amber-600, rojo red-600.
#define C565(r, g, b) ((uint16_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))
static const uint16_t C_FONDO    = C565(0xF1, 0xF5, 0xF9);  // slate-100
static const uint16_t C_TARJETA  = C565(0xFF, 0xFF, 0xFF);
static const uint16_t C_TINTA    = C565(0x0F, 0x17, 0x2A);  // slate-900
static const uint16_t C_GRIS     = C565(0x64, 0x74, 0x8B);  // slate-500
static const uint16_t C_AZUL     = C565(0x25, 0x63, 0xEB);
static const uint16_t C_AZUL_OSC = C565(0x1D, 0x4E, 0xD8);
static const uint16_t C_VERDE    = C565(0x16, 0xA3, 0x4A);  // green-600
static const uint16_t C_AMBAR    = C565(0xD9, 0x77, 0x06);  // amber-600
static const uint16_t C_ROJO     = C565(0xDC, 0x26, 0x26);  // red-600
static const uint16_t C_CLARO    = C565(0xDB, 0xEA, 0xFE);  // texto sobre cabecera

// ── Layout portrait ─────────────────────────────────────────────────────────
static constexpr int PANT_W   = 800;
static constexpr int PANT_H   = 1280;
static constexpr int CAB_H    = 168;
static constexpr int MARGEN   = 24;
static constexpr int Y_BODY   = CAB_H + 24;         // primera tarjeta
static constexpr int TARJ_W   = PANT_W - 2 * MARGEN;
static constexpr int TARJ_H   = 176;
static constexpr int TARJ_GAP = 16;
static constexpr int MAX_OPS  = 5;                  // caben 5 tarjetas holgadas
static constexpr int Y_PIE    = 1196;

// ── Estado global ───────────────────────────────────────────────────────────
struct Op {
    char puesto[48];
    char fase[16];
    char lote[24];
    int  npaq;
};

gfx4desp32_ESP32_P4_101CT_CLB gfx;
HardwareSerial                carroUart(1);
String                        buf;

Op            ops_buf[MAX_OPS];
int           nops        = 0;
int           ops_totales = 0;    // el carro puede tener mas de MAX_OPS
char          carro_id[8] = "--";
char          fw_buf[28]   = "---";
bool          wifi_ok      = false;
unsigned long ultimo_rx    = 0;
unsigned long ultimo_hb    = 0;
unsigned long ultimo_pie   = 0;
bool          tiene_datos   = false;

// ── Helpers de fase ─────────────────────────────────────────────────────────
static uint16_t colorFase(const char *f) {
    if (!strcmp(f, "recoger"))    return C_AMBAR;
    if (!strcmp(f, "trabajando")) return C_AZUL;
    if (!strcmp(f, "devolver"))   return C_VERDE;
    return C_GRIS;   // fin / desconocido
}
static const char *labelFase(const char *f) {
    if (!strcmp(f, "recoger"))    return "RECOGER";
    if (!strcmp(f, "trabajando")) return "EN PROCESO";
    if (!strcmp(f, "devolver"))   return "DEVOLVER";
    if (!strcmp(f, "fin"))        return "FINALIZADO";
    return f;
}

// ── Helpers de texto ────────────────────────────────────────────────────────
static void txtBold(int x, int y, const char *s) {   // seudo-negrita: 2 pasadas
    gfx.MoveTo(x, y);      gfx.print(s);
    gfx.MoveTo(x + 1, y);  gfx.print(s);
}
static void txtDer(int xDer, int y, const char *s) {
    gfx.MoveTo(xDer - gfx.strWidth(s), y);
    gfx.print(s);
}
static void txtCentro(int cx, int y, const char *s) {
    gfx.MoveTo(cx - gfx.strWidth(s) / 2, y);
    gfx.print(s);
}
// Recorta 's' (in situ) con ".." para que quepa en 'maxw' px con la fuente actual.
static void recorta(char *s, int maxw) {
    if (gfx.strWidth(s) <= maxw) return;
    int n = strlen(s);
    while (n > 1) {
        s[--n] = '\0';
        char tmp[64];
        snprintf(tmp, sizeof(tmp), "%s..", s);
        if (gfx.strWidth(tmp) <= maxw) break;
    }
    size_t L = strlen(s);
    if (L + 2 < 48) { s[L] = '.'; s[L + 1] = '.'; s[L + 2] = '\0'; }
}

// ── Dibujo ──────────────────────────────────────────────────────────────────
static void dibujarCabecera() {
    gfx.GradientRectangleFilled(0, 0, PANT_W - 1, CAB_H - 1, C_AZUL, C_AZUL_OSC, true);

    // Marca "COJO sw"
    gfx.Font(1); gfx.TextSize(5); gfx.TextColor(WHITE);
    gfx.MoveTo(MARGEN, 22); gfx.print("COJO");
    int wc = gfx.strWidth("COJO");
    gfx.TextSize(2); gfx.TextColor(C_CLARO);
    gfx.MoveTo(MARGEN + wc + 10, 46); gfx.print("sw");

    // Subtitulo
    char sub[48];
    snprintf(sub, sizeof(sub), "Sistema de Engastado   -   Carro %s", carro_id);
    gfx.Font(2); gfx.TextSize(2); gfx.TextColor(C_CLARO);
    gfx.MoveTo(MARGEN, 106); gfx.print(sub);

    // Pastilla WiFi
    const char *wtxt = wifi_ok ? "WiFi" : "SIN WiFi";
    gfx.Font(2); gfx.TextSize(2);
    int pw = gfx.strWidth(wtxt) + 58;
    int px = PANT_W - MARGEN - pw;
    int py = 24;
    gfx.RoundRectFilledAA(px, py, pw, 44, 22, wifi_ok ? C_VERDE : C_ROJO);
    gfx.CircleFilledAA(px + 22, py + 22, 7, WHITE);
    gfx.TextColor(WHITE);
    gfx.MoveTo(px + 38, py + 9); gfx.print(wtxt);

    // Firmware del carro
    char fwl[40];
    snprintf(fwl, sizeof(fwl), "fw %s", fw_buf);
    gfx.Font(2); gfx.TextSize(1); gfx.TextColor(C_CLARO);
    txtDer(PANT_W - MARGEN, py + 56, fwl);
}

static void dibujarTarjeta(int idx, int y) {
    const Op &o = ops_buf[idx];
    uint16_t cf = colorFase(o.fase);
    int x = MARGEN;

    gfx.RoundRectFilledAA(x, y, TARJ_W, TARJ_H, 18, C_TARJETA);
    gfx.RoundRectFilledAA(x + 16, y + 18, 10, TARJ_H - 36, 5, cf);   // franja de fase

    // Nombre del puesto
    char nom[48];
    strncpy(nom, o.puesto[0] ? o.puesto : "(sin nombre)", sizeof(nom) - 1);
    nom[sizeof(nom) - 1] = '\0';
    gfx.Font(2); gfx.TextSize(3); gfx.TextColor(C_TINTA);
    recorta(nom, TARJ_W - 340);
    txtBold(x + 44, y + 22, nom);

    // Lote
    if (o.lote[0]) {
        char lt[40];
        snprintf(lt, sizeof(lt), "Lote %s", o.lote);
        gfx.Font(2); gfx.TextSize(2); gfx.TextColor(C_GRIS);
        gfx.MoveTo(x + 46, y + 74); gfx.print(lt);
    }

    // Pastilla de fase
    const char *lf = labelFase(o.fase);
    gfx.Font(2); gfx.TextSize(2);
    int pw  = gfx.strWidth(lf) + 44;
    int pxr = x + TARJ_W - 24 - pw;
    gfx.RoundRectFilledAA(pxr, y + 22, pw, 46, 23, cf);
    gfx.TextColor(WHITE);
    gfx.MoveTo(pxr + 22, y + 33); gfx.print(lf);

    // Numero de paquetes
    char num[8];
    snprintf(num, sizeof(num), "%d", o.npaq);
    gfx.Font(1); gfx.TextSize(5); gfx.TextColor(cf);
    gfx.MoveTo(x + 44, y + TARJ_H - 62); gfx.print(num);
    int wn = gfx.strWidth(num);
    gfx.Font(2); gfx.TextSize(2); gfx.TextColor(C_GRIS);
    gfx.MoveTo(x + 44 + wn + 14, y + TARJ_H - 46);
    gfx.print(o.npaq == 1 ? "paquete" : "paquetes");
}

static void dibujarPie() {
    gfx.RectangleFilled(0, Y_PIE - 8, PANT_W - 1, PANT_H - 1, C_FONDO);

    bool ok = tiene_datos;
    gfx.CircleFilledAA(MARGEN + 12, Y_PIE + 24, 9, ok ? C_VERDE : C_ROJO);

    char s[48];
    if (ok) {
        unsigned long seg = (millis() - ultimo_rx) / 1000UL;
        snprintf(s, sizeof(s), "Conectado   -   hace %lus", seg);
    } else {
        snprintf(s, sizeof(s), "SIN DATOS DEL CARRO");
    }
    gfx.Font(2); gfx.TextSize(2); gfx.TextColor(ok ? C_GRIS : C_ROJO);
    gfx.MoveTo(MARGEN + 34, Y_PIE + 12); gfx.print(s);

    if (ops_totales > nops) {
        int resto = ops_totales - nops;
        char m[32];
        snprintf(m, sizeof(m), "y %d puesto%s mas", resto, resto == 1 ? "" : "s");
        gfx.TextColor(C_GRIS);
        txtDer(PANT_W - MARGEN, Y_PIE + 12, m);
    }
}

static void dibujarVacio(const char *titulo, const char *pista) {
    int y = Y_BODY + 40;
    gfx.RoundRectFilledAA(MARGEN, y, TARJ_W, 190, 18, C_TARJETA);
    gfx.Font(2); gfx.TextSize(3); gfx.TextColor(C_GRIS);
    txtCentro(PANT_W / 2, y + 54, titulo);
    if (pista && pista[0]) {
        gfx.Font(2); gfx.TextSize(2); gfx.TextColor(C_GRIS);
        txtCentro(PANT_W / 2, y + 118, pista);
    }
}

static void dibujarPantalla() {
    gfx.Cls(C_FONDO);
    dibujarCabecera();
    if (nops == 0) {
        dibujarVacio("Sin puestos activos", "");
    } else {
        int y = Y_BODY;
        for (int i = 0; i < nops; i++) {
            dibujarTarjeta(i, y);
            y += TARJ_H + TARJ_GAP;
        }
    }
    dibujarPie();
}

// ── Parser JSON ─────────────────────────────────────────────────────────────
static void procesarLinea(const String &msg) {
    Serial.print("RX (");
    Serial.print(msg.length());
    Serial.print("): ");
    Serial.println(msg.substring(0, 120));

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, msg);
    if (err) {
        Serial.print("JSON err: ");
        Serial.println(err.c_str());
        return;
    }

    const char *tipo = doc["tipo"] | "";
    if (strcmp(tipo, "estado") != 0) return;

    strncpy(carro_id, doc["carro"] | "--", sizeof(carro_id) - 1);
    strncpy(fw_buf,   doc["fw"]    | "---", sizeof(fw_buf) - 1);
    carro_id[sizeof(carro_id) - 1] = '\0';
    fw_buf[sizeof(fw_buf) - 1]     = '\0';
    wifi_ok = doc["wifi"] | false;

    JsonArray arr = doc["ops"].as<JsonArray>();
    ops_totales = arr.size();
    nops = 0;
    for (JsonObject op : arr) {
        if (nops >= MAX_OPS) break;
        JsonObject data = op["data"].as<JsonObject>();
        Op &d = ops_buf[nops];
        strncpy(d.puesto, data["puesto_nombre"] | "", sizeof(d.puesto) - 1);
        strncpy(d.fase,   data["fase"]          | "", sizeof(d.fase) - 1);
        strncpy(d.lote,   data["lote"]          | "", sizeof(d.lote) - 1);
        d.puesto[sizeof(d.puesto) - 1] = '\0';
        d.fase[sizeof(d.fase) - 1]     = '\0';
        d.lote[sizeof(d.lote) - 1]     = '\0';
        d.npaq = data["paquetes"].as<JsonArray>().size();
        nops++;
    }

    tiene_datos = true;
    ultimo_rx   = millis();
    dibujarPantalla();
}

// ── Setup / loop ────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    gfx.begin();
    gfx.Cls();
    gfx.ScrollEnable(false);
    gfx.BacklightOn(true);
    gfx.Orientation(PORTRAIT);
    gfx.touch_Set(TOUCH_ENABLE);

    carroUart.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);

    gfx.Cls(C_FONDO);
    dibujarCabecera();
    dibujarVacio("Esperando al carro", "UART1  rx=52  tx=50  115200");
    dibujarPie();

    Serial.println("P4 pantalla_p4_101 v3 (UI) ready");
    Serial.printf("UART1 rx=%d tx=%d baud=%u\n", UART_RX_PIN, UART_TX_PIN, UART_BAUD);
}

void loop() {
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

    unsigned long now = millis();

    // Timeout: sin datos > 90 s
    if (tiene_datos && now - ultimo_rx > 90000UL) {
        tiene_datos = false;
        dibujarPie();
    }

    // Refresco del pie ("hace N s") una vez por segundo
    if (now - ultimo_pie > 1000UL) {
        ultimo_pie = now;
        if (tiene_datos) dibujarPie();
    }

    // Heartbeat + tactil por el monitor serie
    if (now - ultimo_hb > 10000UL) {
        ultimo_hb = now;
        Serial.printf("hb: nops=%d/%d wifi=%d rx_age=%lums\n",
                      nops, ops_totales, (int)wifi_ok,
                      ultimo_rx ? now - ultimo_rx : 0UL);
        gfx.touch_Update();
        if (gfx.touch_GetPen() != NOTOUCH) {
            Serial.printf("TOUCH x=%d y=%d\n", gfx.touch_GetX(), gfx.touch_GetY());
        }
    }
}
