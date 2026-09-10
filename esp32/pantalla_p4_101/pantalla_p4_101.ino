/*
 * pantalla_p4_101.ino
 * Panel de produccion para ESP32-P4 101CT CLB  ·  APAISADO (landscape 1280x800)
 *
 * Recibe de main_wifi.py (carro) por UART1 rx=GPIO52 tx=GPIO50, una trama JSON
 * por linea:
 *   {"v":1,"tipo":"estado","carro":"1","fw":"...","wifi":true,"sel":"puesto_3",
 *    "ops":[{"operario":"puesto_3","data":{"puesto_nombre":"...","puesto_id":"...",
 *       "fase":"recoger|trabajando|devolver","lote":"...","boton":1,
 *       "paquetes":[{"etiqueta":"12","elem":"...","cod":"...","bloqueado":false}]}}]}
 *
 * DOS vistas:
 *   - "sel" vacio  -> LISTA: una fila por puesto con trabajo (boton, nombre,
 *     fase, nº de paquetes). Sin paquetes: con dos o tres puestos seria un caos.
 *   - "sel" = clave de un puesto (alguien paso tarjeta o pulso su boton en el
 *     carro) -> DETALLE: solo ese puesto, con el mosaico de hasta 5 paquetes.
 *
 * Estilo oscuro, a juego con la pantalla pequena del carro: fondo negro, mismos
 * acentos (verde recoger, ambar en proceso, rojo devolver).
 *
 * Refresco SILENCIOSO: se pinta a un frame buffer oculto y se vuelca de golpe,
 * y solo cuando cambia el contenido (huella). El carro reenvia cada 5 s aunque
 * no cambie nada; esas tramas iguales ya no repintan.
 *
 * La linea RX recoge ruido en reposo: se acumula solo desde la '{'.
 *
 * Libreria necesaria: ArduinoJson >=7 (Gestor de librerias Arduino)
 */

#include <Arduino.h>
#include "gfx4desp32_ESP32_P4_101CT_CLB.h"

#define ARDUINOJSON_ENABLE_NAN 1
#define ARDUINOJSON_ENABLE_INFINITY 1
#include <ArduinoJson.h>

// ── UART del carro ───────────────────────────────────────────────────────────
static constexpr int      UART_RX_PIN = 52;
static constexpr int      UART_TX_PIN = 50;
static constexpr uint32_t UART_BAUD   = 115200;

// ── Paleta oscura (RGB565), a juego con la pantalla del carro ───────────────
#define C565(r, g, b) ((uint16_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))
static const uint16_t C_BG     = 0x0000;                 // negro
static const uint16_t C_PANEL  = C565(0x13, 0x1A, 0x28); // panel sobre negro
static const uint16_t C_PANEL2 = C565(0x20, 0x2A, 0x40); // mosaico dentro del panel
static const uint16_t C_LINEA  = C565(0x39, 0x43, 0x55); // separadores
static const uint16_t C_TXT    = 0xFFFF;                 // texto principal
static const uint16_t C_MUTE   = C565(0x8B, 0x98, 0xAF); // texto secundario
static const uint16_t C_VERDE  = C565(0x2F, 0xD1, 0x6B); // recoger
static const uint16_t C_AMBAR  = C565(0xF6, 0xA5, 0x24); // trabajando
static const uint16_t C_ROJO   = C565(0xF2, 0x55, 0x4B); // devolver / alerta
static const uint16_t C_FIN    = C565(0x8B, 0x98, 0xAF); // finalizado

// ── Layout apaisado ─────────────────────────────────────────────────────────
static constexpr int PANT_W    = 1280;
static constexpr int PANT_H    = 800;
static constexpr int CAB_H     = 96;
static constexpr int MARGEN    = 20;
static constexpr int Y_BODY    = CAB_H + 16;
static constexpr int Y_PIE     = 752;
static constexpr int CARD_W    = PANT_W - 2 * MARGEN;
static constexpr int ROW_H     = 76;
static constexpr int ROW_GAP   = 10;
static constexpr int MAX_OPS   = 8;
static constexpr int MAX_ROWS  = 7;
static constexpr int MAX_TILE  = 5;

// ── Estado global ───────────────────────────────────────────────────────────
struct Paq {
    char etiqueta[10];
    char elem[24];
    char cod[18];
    bool bloq;
};
struct Op {
    char clave[40];
    char puesto[40];
    char fase[16];
    char lote[20];
    int  boton;
    int  npaq;
    int  nbuf;
    Paq  paq[MAX_TILE];
};

gfx4desp32_ESP32_P4_101CT_CLB gfx;
HardwareSerial                carroUart(1);
String                        buf;

Op            ops_buf[MAX_OPS];
int           nops        = 0;
char          sel_id[40]  = "";
char          carro_id[8] = "--";
char          fw_buf[28]   = "---";
bool          wifi_ok      = false;
unsigned long ultimo_rx    = 0;
unsigned long ultimo_hb    = 0;
bool          tiene_datos   = false;
unsigned long rx_bytes     = 0;
char          diag[48]      = "sin tramas";
char          lastline[900] = "";
String        pendiente;
bool          hay_pendiente = false;
uint32_t      huella_prev   = 0;

// ── Helpers de fase ─────────────────────────────────────────────────────────
static uint16_t colorFase(const char *f) {
    if (!strcmp(f, "recoger"))    return C_VERDE;
    if (!strcmp(f, "trabajando")) return C_AMBAR;
    if (!strcmp(f, "devolver"))   return C_ROJO;
    return C_FIN;
}
static const char *labelFase(const char *f) {
    if (!strcmp(f, "recoger"))    return "RECOGER";
    if (!strcmp(f, "trabajando")) return "EN PROCESO";
    if (!strcmp(f, "devolver"))   return "DEVOLVER";
    if (!strcmp(f, "fin"))        return "FINALIZADO";
    return f;
}

// ── Helpers de texto ────────────────────────────────────────────────────────
static void txtBold(int x, int y, const char *s) {
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
static void recorta(char *s, int cap, int maxw) {
    if (gfx.strWidth(s) <= maxw) return;
    int n = strlen(s);
    while (n > 1) {
        s[--n] = '\0';
        char tmp[64];
        snprintf(tmp, sizeof(tmp), "%s..", s);
        if (gfx.strWidth(tmp) <= maxw) break;
    }
    int L = strlen(s);
    if (L + 3 <= cap) { s[L] = '.'; s[L + 1] = '.'; s[L + 2] = '\0'; }
}

static void guardarLinea(const String &s) {
    int n = s.length();
    if (n > (int)sizeof(lastline) - 1) n = sizeof(lastline) - 1;
    for (int i = 0; i < n; i++) {
        char c = s[i];
        lastline[i] = (c >= 32 && c < 127) ? c : '.';
    }
    lastline[n] = '\0';
}

// La linea RX recoge ruido en reposo: no se acumula hasta ver la '{', y un
// parcial parado > 150 ms se tira (el ruido gotea, la trama llega en burst).
static unsigned long ultimo_byte = 0;

static void pump() {
    while (carroUart.available()) {
        char c = static_cast<char>(carroUart.read());
        rx_bytes++;
        ultimo_byte = millis();
        if (c == '\n') {
            String s = buf; buf = ""; s.trim();
            if (s.length() > 1 && s[0] == '{') { pendiente = s; hay_pendiente = true; }
            else if (s.length() > 0)
                snprintf(diag, sizeof(diag), "linea sin JSON (%u B ruido)", (unsigned)s.length());
        } else if (buf.length() == 0) {
            if (c == '{') buf += c;
        } else if (c != '\r' && buf.length() < 8192) {
            buf += c;
        } else if (buf.length() >= 8192) {
            snprintf(diag, sizeof(diag), "overflow (%lu B)", rx_bytes);
            buf = "";
        }
    }
    if (buf.length() > 0 && millis() - ultimo_byte > 150) buf = "";
}

static void copiaCampo(char *dst, size_t n, JsonVariant v, const char *def) {
    if (v.isNull()) { strncpy(dst, def, n - 1); dst[n - 1] = '\0'; return; }
    if (v.is<const char *>()) { strncpy(dst, v.as<const char *>(), n - 1); dst[n - 1] = '\0'; return; }
    String s = v.as<String>();
    strncpy(dst, s.c_str(), n - 1);
    dst[n - 1] = '\0';
}

// ── Huella del contenido (para no repintar si nada cambia) ──────────────────
static uint32_t fnv(const char *s, uint32_t h) {
    while (*s) { h ^= (uint8_t)*s++; h *= 16777619u; }
    return h;
}
static int selIndex() {
    if (!sel_id[0]) return -1;
    for (int i = 0; i < nops; i++)
        if (!strcmp(ops_buf[i].clave, sel_id)) return i;
    return -1;
}
static uint32_t huellaActual() {
    uint32_t h = 2166136261u;
    char t[80];
    snprintf(t, sizeof(t), "%s|%s|%d|%d|%d", sel_id, carro_id, (int)wifi_ok, nops, (int)tiene_datos);
    h = fnv(t, h);
    if (!tiene_datos) {
        snprintf(t, sizeof(t), "R%lu|%s", rx_bytes >> 10, diag);
        return fnv(t, h);
    }
    int si = selIndex();
    if (si >= 0) {
        const Op &o = ops_buf[si];
        snprintf(t, sizeof(t), "D%s|%s|%s|%d|%d", o.puesto, o.fase, o.lote, o.npaq, o.nbuf);
        h = fnv(t, h);
        for (int k = 0; k < o.nbuf; k++) {
            snprintf(t, sizeof(t), "%s|%s|%d", o.paq[k].etiqueta, o.paq[k].elem, (int)o.paq[k].bloq);
            h = fnv(t, h);
        }
    } else {
        int vis = nops < MAX_ROWS ? nops : MAX_ROWS;
        for (int i = 0; i < vis; i++) {
            const Op &o = ops_buf[i];
            snprintf(t, sizeof(t), "L%s|%s|%d|%d", o.puesto, o.fase, o.boton, o.npaq);
            h = fnv(t, h);
        }
    }
    return h;
}

// ── Cabecera ────────────────────────────────────────────────────────────────
static void dibujarCabecera() {
    gfx.Font(2); gfx.TextSize(4); gfx.TextColor(C_TXT);
    gfx.MoveTo(MARGEN, 14); gfx.print("COJO");
    int wc = gfx.strWidth("COJO");
    gfx.TextSize(2); gfx.TextColor(C_MUTE);
    gfx.MoveTo(MARGEN + wc + 8, 30); gfx.print("sw");
    gfx.TextColor(C_AMBAR);
    gfx.MoveTo(MARGEN, 60); gfx.print("ENGASTADO");

    char ct[24];
    snprintf(ct, sizeof(ct), "CARRO %s", carro_id);
    gfx.Font(2); gfx.TextSize(4); gfx.TextColor(C_TXT);
    txtCentro(PANT_W / 2, 22, ct);

    const char *wtxt = wifi_ok ? "WiFi" : "SIN WiFi";
    gfx.Font(2); gfx.TextSize(2); gfx.TextColor(wifi_ok ? C_VERDE : C_ROJO);
    gfx.CircleFilledAA(PANT_W - MARGEN - gfx.strWidth(wtxt) - 20, 30, 7, wifi_ok ? C_VERDE : C_ROJO);
    txtDer(PANT_W - MARGEN, 20, wtxt);

    char fwl[40];
    snprintf(fwl, sizeof(fwl), "fw %s", fw_buf);
    gfx.Font(2); gfx.TextSize(1); gfx.TextColor(C_MUTE);
    txtDer(PANT_W - MARGEN, 58, fwl);

    gfx.Hline(0, CAB_H - 1, PANT_W, C_LINEA);
}

// ── Pastilla de fase ────────────────────────────────────────────────────────
static void pastillaFase(int xDer, int y, int sz, const char *f) {
    const char *lf = labelFase(f);
    gfx.Font(2); gfx.TextSize(sz);
    int pw = gfx.strWidth(lf) + 20 * sz;
    int px = xDer - pw;
    int hh = 14 + 10 * sz;
    gfx.RoundRectFilledAA(px, y, pw, hh, hh / 2, colorFase(f));
    gfx.TextColor(C_BG);
    gfx.MoveTo(px + 10 * sz, y + (hh - 8 * sz) / 2 - 1);
    gfx.print(lf);
}

// ── Vista LISTA ─────────────────────────────────────────────────────────────
static void dibujarFila(int idx, int y) {
    const Op &o = ops_buf[idx];
    uint16_t cf = colorFase(o.fase);
    int x = MARGEN;

    gfx.RoundRectFilledAA(x, y, CARD_W, ROW_H, 12, C_PANEL);

    int badge = ROW_H - 26;
    if (o.boton > 0) {
        gfx.RoundRectFilledAA(x + 14, y + 13, badge, badge, 12, cf);
        char b[4]; snprintf(b, sizeof(b), "%d", o.boton);
        gfx.Font(2); gfx.TextSize(3); gfx.TextColor(C_BG);
        txtCentro(x + 14 + badge / 2, y + 13 + (badge - 24) / 2, b);
    } else {
        gfx.CircleFilledAA(x + 14 + badge / 2, y + ROW_H / 2, 12, cf);
    }

    char nom[40];
    strncpy(nom, o.puesto[0] ? o.puesto : "(sin nombre)", sizeof(nom) - 1);
    nom[sizeof(nom) - 1] = '\0';
    gfx.Font(2); gfx.TextSize(3); gfx.TextColor(C_TXT);
    recorta(nom, sizeof(nom), 560);
    txtBold(x + 90, y + (ROW_H - 24) / 2, nom);

    int pastDer = x + CARD_W - 20;
    pastillaFase(pastDer, y + 16, 2, o.fase);

    const char *lf = labelFase(o.fase);
    gfx.Font(2); gfx.TextSize(2);
    int pw = gfx.strWidth(lf) + 40;
    char np[20];
    snprintf(np, sizeof(np), "%d paq", o.npaq);
    gfx.TextColor(C_MUTE);
    txtDer(pastDer - pw - 24, y + 24, np);
}

static void dibujarLista(bool aviso_sel) {
    int y = Y_BODY;
    if (aviso_sel) {
        gfx.RoundRectFilledAA(MARGEN, y, CARD_W, 48, 12, C_PANEL);
        gfx.Font(2); gfx.TextSize(2); gfx.TextColor(C_MUTE);
        gfx.MoveTo(MARGEN + 22, y + 12);
        gfx.print("El puesto identificado no tiene paquetes en este carro");
        y += 48 + ROW_GAP;
    }
    if (nops == 0) {
        gfx.RoundRectFilledAA(MARGEN, y, CARD_W, 200, 16, C_PANEL);
        gfx.Font(2); gfx.TextSize(4); gfx.TextColor(C_MUTE);
        txtCentro(PANT_W / 2, y + 70, "Sin trabajo en el carro");
        return;
    }
    int vis = nops < MAX_ROWS ? nops : MAX_ROWS;
    for (int i = 0; i < vis; i++) {
        dibujarFila(i, y);
        y += ROW_H + ROW_GAP;
    }
}

// ── Vista DETALLE ───────────────────────────────────────────────────────────
static void dibujarTile(int tileX, int tileY, int tileW, int tileH, const Paq &p) {
    gfx.RoundRectFilledAA(tileX, tileY, tileW, tileH, 12, C_PANEL2);

    int len = strlen(p.etiqueta);
    int sz  = (len <= 2) ? 8 : (len == 3) ? 6 : 5;
    gfx.Font(2); gfx.TextSize(sz);
    gfx.TextColor(p.bloq ? C_MUTE : C_TXT);
    txtCentro(tileX + tileW / 2, tileY + 26, p.etiqueta[0] ? p.etiqueta : "-");

    int ty = tileY + 26 + 8 * sz + 18;
    if (p.elem[0]) {
        char e[24];
        strncpy(e, p.elem, sizeof(e) - 1); e[sizeof(e) - 1] = '\0';
        gfx.Font(2); gfx.TextSize(2); gfx.TextColor(C_TXT);
        recorta(e, sizeof(e), tileW - 20);
        txtCentro(tileX + tileW / 2, ty, e);
        ty += 34;
    }
    if (p.cod[0]) {
        char c[18];
        strncpy(c, p.cod, sizeof(c) - 1); c[sizeof(c) - 1] = '\0';
        gfx.Font(2); gfx.TextSize(1); gfx.TextColor(C_MUTE);
        recorta(c, sizeof(c), tileW - 20);
        txtCentro(tileX + tileW / 2, ty, c);
    }

    if (p.bloq) {
        gfx.RoundRectFilledAA(tileX, tileY + tileH - 30, tileW, 30, 12, C_ROJO);
        gfx.Font(2); gfx.TextSize(1); gfx.TextColor(C_BG);
        txtCentro(tileX + tileW / 2, tileY + tileH - 25, "BLOQUEADO");
    }
}

static void dibujarDetalle(int idx) {
    const Op &o = ops_buf[idx];
    uint16_t cf = colorFase(o.fase);
    int x = MARGEN, y = Y_BODY, h = Y_PIE - Y_BODY - 8;

    gfx.RoundRectFilledAA(x, y, CARD_W, h, 16, C_PANEL);
    gfx.RoundRectFilledAA(x + 12, y + 16, 8, h - 32, 4, cf);

    int pastDer = x + CARD_W - 24;
    pastillaFase(pastDer, y + 18, 3, o.fase);

    const char *lf = labelFase(o.fase);
    gfx.Font(2); gfx.TextSize(3);
    int pw = gfx.strWidth(lf) + 60;

    char nom[40];
    strncpy(nom, o.puesto[0] ? o.puesto : "(sin nombre)", sizeof(nom) - 1);
    nom[sizeof(nom) - 1] = '\0';
    gfx.Font(2); gfx.TextSize(4); gfx.TextColor(C_TXT);
    recorta(nom, sizeof(nom), pastDer - pw - (x + 40) - 20);
    txtBold(x + 40, y + 20, nom);

    char meta[56];
    if (o.lote[0]) snprintf(meta, sizeof(meta), "Lote %s     -     %d paquetes", o.lote, o.npaq);
    else           snprintf(meta, sizeof(meta), "%d paquetes", o.npaq);
    gfx.Font(2); gfx.TextSize(2); gfx.TextColor(C_MUTE);
    gfx.MoveTo(x + 42, y + 84); gfx.print(meta);

    int tileY = y + 126;
    int tileH = h - 126 - 24;
    if (o.nbuf <= 0) {
        gfx.Font(2); gfx.TextSize(3); gfx.TextColor(C_MUTE);
        txtCentro(PANT_W / 2, tileY + tileH / 2 - 20, "Sin paquetes");
        return;
    }
    int area  = CARD_W - 64;
    int tileW = (area - (MAX_TILE - 1) * 14) / MAX_TILE;
    int nreal = o.nbuf;
    bool overflow = (o.npaq > o.nbuf);
    if (overflow && nreal == MAX_TILE) nreal = MAX_TILE - 1;
    int tx = x + 40;
    for (int t = 0; t < nreal; t++) {
        dibujarTile(tx, tileY, tileW, tileH, o.paq[t]);
        tx += tileW + 14;
    }
    if (overflow) {
        gfx.RoundRectFilledAA(tx, tileY, tileW, tileH, 12, C_PANEL2);
        char mas[16];
        snprintf(mas, sizeof(mas), "+%d", o.npaq - nreal);
        gfx.Font(2); gfx.TextSize(7); gfx.TextColor(C_MUTE);
        txtCentro(tx + tileW / 2, tileY + tileH / 2 - 40, mas);
        gfx.Font(2); gfx.TextSize(2);
        txtCentro(tx + tileW / 2, tileY + tileH / 2 + 34, "mas");
    }
}

// ── Espera / diagnostico ───────────────────────────────────────────────────
static void dibujarEspera() {
    int y = Y_BODY + 30;
    gfx.RoundRectFilledAA(MARGEN, y, CARD_W, 220, 16, C_PANEL);
    gfx.Font(2); gfx.TextSize(4); gfx.TextColor(C_MUTE);
    txtCentro(PANT_W / 2, y + 84, "Esperando al carro");
    gfx.Font(2); gfx.TextSize(2);
    txtCentro(PANT_W / 2, y + 158, "UART1  rx=52  tx=50  115200");
}

static void dibujarDiagnostico() {
    int x = MARGEN, y = Y_BODY + 12, w = CARD_W, h = Y_PIE - y - 10;
    gfx.RoundRectFilledAA(x, y, w, h, 16, C_PANEL);

    gfx.Font(2); gfx.TextSize(3); gfx.TextColor(C_ROJO);
    gfx.MoveTo(x + 34, y + 24); gfx.print("Llegan bytes pero no son una trama valida");

    char l1[110];
    snprintf(l1, sizeof(l1), "UART1 rx=52 tx=50  115200   |   %lu B recibidos   |   buf %d B",
             rx_bytes, buf.length());
    gfx.Font(2); gfx.TextSize(2); gfx.TextColor(C_TXT);
    gfx.MoveTo(x + 34, y + 84); gfx.print(l1);
    char l2[90];
    snprintf(l2, sizeof(l2), "ultimo parseo:  %s", diag);
    gfx.MoveTo(x + 34, y + 122); gfx.print(l2);

    gfx.Font(2); gfx.TextSize(2); gfx.TextColor(C_MUTE);
    gfx.MoveTo(x + 34, y + 172); gfx.print("ultima linea recibida:");
    gfx.Font(2); gfx.TextSize(1); gfx.TextColor(C_TXT);
    int py = y + 204;
    int L = strlen(lastline);
    for (int off = 0; off < L && py < y + h - 16; off += 82) {
        char seg[84];
        strncpy(seg, lastline + off, 82); seg[82] = '\0';
        gfx.MoveTo(x + 34, py); gfx.print(seg);
        py += 22;
    }
    if (L == 0) { gfx.MoveTo(x + 34, py); gfx.print("(vacia)"); }
}

// ── Pie ─────────────────────────────────────────────────────────────────────
static void dibujarPie() {
    gfx.Hline(0, Y_PIE - 1, PANT_W, C_LINEA);
    bool ok = tiene_datos;
    gfx.CircleFilledAA(MARGEN + 12, Y_PIE + 22, 8, ok ? C_VERDE : C_ROJO);
    gfx.Font(2); gfx.TextSize(2); gfx.TextColor(ok ? C_MUTE : C_ROJO);
    gfx.MoveTo(MARGEN + 34, Y_PIE + 12);
    gfx.print(ok ? "Conectado" : "SIN DATOS DEL CARRO");

    if (!ok && rx_bytes > 0) {
        char d2[120];
        snprintf(d2, sizeof(d2), "%lu B por la UART   -   %s", rx_bytes, diag);
        gfx.Font(2); gfx.TextSize(1); gfx.TextColor(C_MUTE);
        txtDer(PANT_W - MARGEN, Y_PIE + 18, d2);
    } else if (!sel_id[0] && nops > MAX_ROWS) {
        char m[32];
        snprintf(m, sizeof(m), "y %d puesto%s mas", nops - MAX_ROWS, nops - MAX_ROWS == 1 ? "" : "s");
        gfx.Font(2); gfx.TextSize(2); gfx.TextColor(C_MUTE);
        txtDer(PANT_W - MARGEN, Y_PIE + 12, m);
    }
}

// ── Render (a frame buffer oculto, volcado de golpe) ────────────────────────
static void render() {
    gfx.DrawToframebuffer(1);
    gfx.Cls(C_BG);
    dibujarCabecera();
    if (!tiene_datos && rx_bytes == 0)      dibujarEspera();
    else if (!tiene_datos)                  dibujarDiagnostico();
    else {
        int si = selIndex();
        if (si >= 0) dibujarDetalle(si);
        else         dibujarLista(sel_id[0] != '\0');
    }
    dibujarPie();
    gfx.DrawToframebuffer(0);
    gfx.DrawFrameBuffer(1);
}

static void actualizar(bool forzar) {
    uint32_t h = huellaActual();
    if (!forzar && h == huella_prev) return;
    huella_prev = h;
    render();
}

// ── Parser JSON ─────────────────────────────────────────────────────────────
static void procesarLinea(const String &msg) {
    Serial.print("RX (");
    Serial.print(msg.length());
    Serial.print("): ");
    Serial.println(msg.substring(0, 140));

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, msg.c_str(), msg.length());
    if (err) {
        const char *p = msg.c_str();
        int len = msg.length();
        for (int b = 1; b < len && b < 400 && err; b++) {
            if (p[b] != '{') continue;
            DeserializationError e2 = deserializeJson(doc, p + b, len - b);
            if (!e2) { err = e2; Serial.printf("recuperado tras %d bytes de ruido\n", b); }
        }
    }
    if (err) {
        snprintf(diag, sizeof(diag), "JSON err: %s", err.c_str());
        Serial.print("JSON err: "); Serial.println(err.c_str());
        Serial.print("  raw: ");
        for (int i = 0; i < (int)msg.length() && i < 64; i++)
            Serial.printf("%02X ", (uint8_t)msg[i]);
        Serial.println();
        if (!tiene_datos) actualizar(false);
        return;
    }

    const char *tipo = doc["tipo"] | "";
    if (strcmp(tipo, "estado") != 0) {
        snprintf(diag, sizeof(diag), "tipo '%s' ignorado", tipo);
        if (!tiene_datos) actualizar(false);
        return;
    }

    copiaCampo(carro_id, sizeof(carro_id), doc["carro"], "--");
    copiaCampo(fw_buf,   sizeof(fw_buf),   doc["fw"],    "---");
    copiaCampo(sel_id,   sizeof(sel_id),   doc["sel"],   "");
    wifi_ok = doc["wifi"] | false;

    JsonArray arr = doc["ops"].as<JsonArray>();
    nops = 0;
    for (JsonObject op : arr) {
        if (nops >= MAX_OPS) break;
        JsonObject data = op["data"].as<JsonObject>();
        Op &d = ops_buf[nops];
        copiaCampo(d.puesto, sizeof(d.puesto), data["puesto_nombre"], "");
        copiaCampo(d.fase,   sizeof(d.fase),   data["fase"],          "");
        copiaCampo(d.lote,   sizeof(d.lote),   data["lote"],          "");
        if (!data["puesto_id"].isNull())
            copiaCampo(d.clave, sizeof(d.clave), data["puesto_id"], "");
        else
            copiaCampo(d.clave, sizeof(d.clave), op["operario"], "");
        d.boton = data["boton"] | 0;

        JsonArray paq = data["paquetes"].as<JsonArray>();
        d.npaq = paq.size();
        d.nbuf = 0;
        for (JsonObject p : paq) {
            if (d.nbuf >= MAX_TILE) break;
            Paq &q = d.paq[d.nbuf];
            copiaCampo(q.etiqueta, sizeof(q.etiqueta), p["etiqueta"], "-");
            copiaCampo(q.elem,     sizeof(q.elem),     p["elem"],     "");
            copiaCampo(q.cod,      sizeof(q.cod),      p["cod"],      "");
            q.bloq = p["bloqueado"] | false;
            d.nbuf++;
        }
        nops++;
    }

    snprintf(diag, sizeof(diag), "OK %d puesto%s%s", nops, nops == 1 ? "" : "s",
             sel_id[0] ? " (detalle)" : "");
    tiene_datos = true;
    ultimo_rx   = millis();
    actualizar(false);
}

// ── Setup / loop ────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    gfx.begin();
    gfx.Cls();
    gfx.ScrollEnable(false);
    gfx.BacklightOn(true);
    gfx.Orientation(LANDSCAPE);
    gfx.touch_Set(TOUCH_ENABLE);

    buf.reserve(2048);
    carroUart.setRxBufferSize(4096);
    carroUart.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);

    actualizar(true);   // pantalla de espera

    Serial.println("P4 pantalla_p4_101 v6 (oscuro, refresco silencioso) ready");
    Serial.printf("UART1 rx=%d tx=%d baud=%lu rxbuf=4096\n", UART_RX_PIN, UART_TX_PIN,
                  (unsigned long)UART_BAUD);
}

void loop() {
    pump();
    if (hay_pendiente) {
        hay_pendiente = false;
        String linea = pendiente;
        guardarLinea(linea);
        procesarLinea(linea);
    }

    unsigned long now = millis();

    if (tiene_datos && now - ultimo_rx > 90000UL) {
        tiene_datos = false;
        snprintf(diag, sizeof(diag), "timeout 90 s sin trama");
        actualizar(true);
    }

    if (now - ultimo_hb > 10000UL) {
        ultimo_hb = now;
        Serial.printf("hb: rx=%luB buf=%d nops=%d sel='%s' wifi=%d rx_age=%lums | %s\n",
                      rx_bytes, buf.length(), nops, sel_id, (int)wifi_ok,
                      ultimo_rx ? now - ultimo_rx : 0UL, diag);
        if (!tiene_datos && lastline[0]) {
            Serial.print("LASTLINE["); Serial.print((int)strlen(lastline));
            Serial.print("]: "); Serial.println(lastline);
        }
        gfx.touch_Update();
        if (gfx.touch_GetPen() != NOTOUCH) {
            Serial.printf("TOUCH x=%d y=%d\n", gfx.touch_GetX(), gfx.touch_GetY());
        }
    }
}
