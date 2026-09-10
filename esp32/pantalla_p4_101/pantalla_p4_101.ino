/*
 * pantalla_p4_101.ino
 * Panel de produccion para ESP32-P4 101CT CLB  ·  APAISADO (1280x800)
 *
 * Interfaz con LVGL 9: tipos de letra suavizados, tarjetas con esquinas
 * redondeadas y sombra, tema oscuro. La placa 4D (GFX4dESP32P4) se usa solo
 * para encender el panel MIPI, la retro y el tactil; LVGL pinta directamente
 * en su framebuffer (SelectFB(0)), que el controlador DSI refresca solo.
 *
 * Recibe del carro (main_wifi.py) por UART1 rx=GPIO52 tx=GPIO50, una trama
 * JSON por linea:
 *   {"v":1,"tipo":"estado","carro":"1","fw":"...","wifi":true,"sel":"puesto_3",
 *    "ops":[{"operario":"puesto_3","data":{"puesto_nombre":"...","puesto_id":"...",
 *       "fase":"recoger|trabajando|devolver","lote":"...","boton":1,
 *       "grupo":1,"grupos":5,"paquetes":[{"etiqueta":12,"elem":"S206","cod":"...",
 *          "cables":3,"term":5,"color":"#2563eb","tcolor":"#ffffff","bloqueado":false}]}}]}
 *
 *   - "sel" vacio  -> LISTA: una fila por puesto (boton, nombre, fase, nº paq).
 *   - "sel" = clave -> DETALLE: ese puesto con sus paquetes en un grid de 5
 *     (3 arriba, 2 abajo). Cada celda lleva el nº de etiqueta enorme y el
 *     nombre del elemento, con el fondo del color de la etiqueta (el mismo
 *     color que usa el modal del SW web) y los contadores cables / term.
 *
 * Requiere, ademas de GFX4dESP32P4 y ArduinoJson, la libreria LVGL 9:
 *     arduino-cli lib install lvgl
 * La config es lv_conf.h de esta misma carpeta.
 */

#include <Arduino.h>
#include <lvgl.h>
#include "gfx4desp32_ESP32_P4_101CT_CLB.h"
#include "esp_cache.h"   // esp_cache_msync: volcar la cache al framebuffer PSRAM
#include <Preferences.h> // NVS: guardar la calibracion tactil
#include <Wire.h>        // sonda I2C del GT911 al arrancar
#include <math.h>        // lround, fabs, sqrt (ajuste afin de la calibracion)

#define ARDUINOJSON_ENABLE_NAN 1
#define ARDUINOJSON_ENABLE_INFINITY 1
#include <ArduinoJson.h>

// ── UART del carro ───────────────────────────────────────────────────────────
static constexpr int      UART_RX_PIN = 52;
static constexpr int      UART_TX_PIN = 50;
static constexpr uint32_t UART_BAUD   = 115200;

// ── Panel ───────────────────────────────────────────────────────────────────
static constexpr int NAT_W = 800;    // framebuffer nativo (vertical)
static constexpr int NAT_H = 1280;
static constexpr int LV_W  = 1280;   // interfaz en apaisado
static constexpr int LV_H  = 800;

// ── Paleta oscura ───────────────────────────────────────────────────────────
#define COL_BG      lv_color_hex(0x0B0F17)
#define COL_PANEL   lv_color_hex(0x161E2E)
#define COL_PANEL2  lv_color_hex(0x212C42)
#define COL_TXT     lv_color_hex(0xF4F7FB)
#define COL_MUTE    lv_color_hex(0x8B98AF)
#define COL_LINE    lv_color_hex(0x2A3446)
#define COL_VERDE   lv_color_hex(0x30D46A)
#define COL_AMBAR   lv_color_hex(0xF6A524)
#define COL_ROJO    lv_color_hex(0xF2554B)
#define COL_AZUL    lv_color_hex(0x4D96FF)   /* acento azul (reserva de paleta) */
#define COL_NEGRO   lv_color_hex(0x0B0F17)

#define F_XS   &lv_font_montserrat_14
#define F_SM   &lv_font_montserrat_18
#define F_MD   &lv_font_montserrat_24
#define F_LG   &lv_font_montserrat_36
#define F_XL   &lv_font_montserrat_48
// Nº de etiqueta: Montserrat Bold 128 px (solo digitos y '-'), generada con
// lv_font_conv y embebida en lv_font_num128.c. LVGL no trae fuentes >48.
// El .c se compila como C: hace falta enlace C para que resuelva el simbolo.
extern "C" const lv_font_t lv_font_num128;
#define F_HUGE &lv_font_num128

// ── Estado (datos del carro) ────────────────────────────────────────────────
static constexpr int MAX_OPS  = 8;
static constexpr int MAX_ROWS = 7;
static constexpr int MAX_TILE = 5;

struct Paq { char etiqueta[10]; char elem[24]; char cod[18]; int cables; int term; bool bloq;
             uint32_t rgb; uint32_t trgb; };   // rgb = color de la etiqueta; trgb = color de texto
struct Op {
    char clave[40]; char puesto[40]; char fase[16]; char lote[20];
    int  boton; int npaq; int nbuf; int grupo; int grupos; Paq paq[MAX_TILE];
};

Op            ops_buf[MAX_OPS];
int           nops        = 0;
char          sel_id[40]  = "";
char          carro_id[8] = "--";
char          fw_buf[28]   = "---";
bool          wifi_ok      = false;
bool          pide_ok      = false;   // el carro pide confirmar el puesto en detalle
unsigned long ultimo_rx    = 0;
unsigned long ultimo_hb    = 0;
bool          tiene_datos   = false;
unsigned long rx_bytes     = 0;
char          diag[48]      = "sin tramas";
char          lastline[900] = "";
uint32_t      huella_prev   = 0;

// ── UART ────────────────────────────────────────────────────────────────────
gfx4desp32_ESP32_P4_101CT_CLB gfx;
HardwareSerial                carroUart(1);
String                        buf;
String                        pendiente;
bool                          hay_pendiente = false;
static unsigned long          ultimo_byte   = 0;
uint8_t*                      fb            = nullptr;

// ── LVGL: objetos persistentes ─────────────────────────────────────────────
static lv_obj_t *lbl_carro, *lbl_wifi, *lbl_fw, *cont;

// ── Tactil: velo de confirmacion + diagnostico ────────────────────────────
// La libreria 4D entrega el toque ya "rotado" segun su propio 'rotation', y
// sin llamar a gfx.Orientation() sus ejes no cuadran con la rotacion manual
// que hace flush_cb -> el toque caia fuera de la barra CONFIRMAR. Mientras se
// afina el mapa exacto (rotulo TOUCH_DEBUG de abajo), un velo transparente
// sobre TODA la pantalla capta el toque en cualquier punto cuando el carro
// pide OK: cumple lo pedido ("Enter / barra espaciadora en toda la zona").
static lv_obj_t *ok_overlay = nullptr;

#define TOUCH_DEBUG 0   // 1 = rotulo de diagnostico tactil abajo-izquierda
#if TOUCH_DEBUG
static lv_obj_t         *lbl_dbg   = nullptr;
static volatile int      dbg_pen   = 0, dbg_rawx = 0, dbg_rawy = 0, dbg_mapx = 0, dbg_mapy = 0;
static volatile uint32_t dbg_ms    = 0;
static volatile uint32_t dbg_clicks = 0;
#endif

// ── Calibracion tactil (mapa afin raw -> LVGL) ────────────────────────────
// La libreria 4D entrega el toque en un sistema propio que, sin llamar a
// gfx.Orientation(), no cuadra con la rotacion manual que hace flush_cb. En
// vez de deducir la formula a mano, el panel pide 5 toques sobre unas cruces
// al arrancar y ajusta por minimos cuadrados:
//     lx = ax*rawx + bx*rawy + cx ;  ly = ay*rawx + by*rawy + cy
// Un afin absorbe cualquier giro/espejo/escala. Se guarda en NVS; en arranques
// posteriores hay una ventana corta para repetir la calibracion.
static Preferences prefs;
static bool   cal_valida = false;
static double cal_ax = 1, cal_bx = 0, cal_cx = 0;
static double cal_ay = 0, cal_by = 1, cal_cy = 0;
static char   cal_i2c[24] = "?";   // resultado de la sonda I2C del GT911

// Lee el tactil SIN pasar por el gate del pin INT de touch_Update() (que en
// esta placa lo dejaba mudo: nunca detectaba la pulsacion). touch_GetTouchPoints
// consulta el GT911 por I2C directamente. Devuelve true con el crudo del 1er
// contacto; el mapa afin de la calibracion lo convierte a coordenadas LVGL.
static bool touch_raw(int *x, int *y) {
    int tx[5], ty[5];
    int n = gfx.touch_GetTouchPoints(tx, ty);
    if (n <= 0) return false;
    *x = tx[0];
    *y = ty[0];
    return true;
}

// ── Helpers de fase ─────────────────────────────────────────────────────────
static lv_color_t colorFase(const char *f) {
    if (!strcmp(f, "recoger"))    return COL_VERDE;
    if (!strcmp(f, "trabajando")) return COL_AMBAR;
    if (!strcmp(f, "devolver"))   return COL_ROJO;
    return COL_MUTE;
}
static const char *labelFase(const char *f) {
    if (!strcmp(f, "recoger"))    return "RECOGER";
    if (!strcmp(f, "trabajando")) return "EN PROCESO";
    if (!strcmp(f, "devolver"))   return "DEVOLVER";
    if (!strcmp(f, "fin"))        return "FINALIZADO";
    return f;
}

// ── UART: drenar sin parsear (ruido en reposo -> acumular solo desde '{') ───
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

// "#rrggbb" o "rrggbb" -> 0xRRGGBB. Devuelve def si no hay 6 hex validos.
static uint32_t parseHexColor(JsonVariant v, uint32_t def) {
    if (!v.is<const char *>()) return def;
    const char *s = v.as<const char *>();
    if (!s) return def;
    if (*s == '#') s++;
    uint32_t out = 0; int n = 0;
    for (; n < 6 && s[n]; n++) {
        char c = s[n]; uint32_t d;
        if      (c >= '0' && c <= '9') d = c - '0';
        else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
        else return def;
        out = (out << 4) | d;
    }
    return n == 6 ? out : def;
}

static void copiaCampo(char *dst, size_t n, JsonVariant v, const char *def) {
    if (v.isNull()) { strncpy(dst, def, n - 1); dst[n - 1] = '\0'; return; }
    if (v.is<const char *>()) { strncpy(dst, v.as<const char *>(), n - 1); dst[n - 1] = '\0'; return; }
    String s = v.as<String>();
    strncpy(dst, s.c_str(), n - 1);
    dst[n - 1] = '\0';
}
static void guardarLinea(const String &s) {
    int n = s.length();
    if (n > (int)sizeof(lastline) - 1) n = sizeof(lastline) - 1;
    for (int i = 0; i < n; i++) { char c = s[i]; lastline[i] = (c >= 32 && c < 127) ? c : '.'; }
    lastline[n] = '\0';
}

// ── Huella del contenido ───────────────────────────────────────────────────
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
    if (!tiene_datos) { snprintf(t, sizeof(t), "R%lu|%s", rx_bytes >> 10, diag); return fnv(t, h); }
    int si = selIndex();
    if (si >= 0) {
        const Op &o = ops_buf[si];
        snprintf(t, sizeof(t), "D%s|%s|%s|%d|%d|%d|%d|%d", o.puesto, o.fase, o.lote,
                 o.npaq, o.nbuf, o.grupo, o.grupos, (int)pide_ok);
        h = fnv(t, h);
        for (int k = 0; k < o.nbuf; k++) {
            const Paq &q = o.paq[k];
            snprintf(t, sizeof(t), "%s|%s|%d|%d|%d|%lu", q.etiqueta, q.elem,
                     q.cables, q.term, (int)q.bloq, (unsigned long)q.rgb);
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

// ── LVGL: helpers de estilo ────────────────────────────────────────────────
static lv_obj_t *card(lv_obj_t *parent, lv_color_t accent) {
    lv_obj_t *c = lv_obj_create(parent);
    lv_obj_set_width(c, LV_PCT(100));
    lv_obj_set_style_bg_color(c, COL_PANEL, 0);
    lv_obj_set_style_bg_opa(c, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(c, 16, 0);
    lv_obj_set_style_border_width(c, 0, 0);
    lv_obj_set_style_border_side(c, LV_BORDER_SIDE_LEFT, 0);
    lv_obj_set_style_border_color(c, accent, 0);
    lv_obj_set_style_border_width(c, 6, 0);
    lv_obj_set_style_shadow_width(c, 24, 0);
    lv_obj_set_style_shadow_opa(c, LV_OPA_40, 0);
    lv_obj_set_style_shadow_color(c, lv_color_black(), 0);
    lv_obj_set_style_shadow_offset_y(c, 6, 0);
    lv_obj_set_style_pad_all(c, 16, 0);
    lv_obj_remove_flag(c, LV_OBJ_FLAG_SCROLLABLE);
    return c;
}
static lv_obj_t *chip(lv_obj_t *parent, const char *txt, lv_color_t bg, const lv_font_t *fnt) {
    lv_obj_t *l = lv_label_create(parent);
    lv_label_set_text(l, txt);
    lv_obj_set_style_text_font(l, fnt, 0);
    lv_obj_set_style_text_color(l, COL_NEGRO, 0);
    lv_obj_set_style_bg_color(l, bg, 0);
    lv_obj_set_style_bg_opa(l, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(l, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_pad_hor(l, 16, 0);
    lv_obj_set_style_pad_ver(l, 6, 0);
    return l;
}
static lv_obj_t *txt(lv_obj_t *parent, const char *s, const lv_font_t *fnt, lv_color_t col) {
    lv_obj_t *l = lv_label_create(parent);
    lv_label_set_text(l, s);
    lv_obj_set_style_text_font(l, fnt, 0);
    lv_obj_set_style_text_color(l, col, 0);
    return l;
}

// ── OK tactil -> carro ─────────────────────────────────────────────────────
// El boton solo sale cuando el carro pide confirmacion (campo "ok" de la
// trama). Al tocarlo se manda {"tipo":"ok",...} al carro por la misma UART y
// se reintenta (3x cada 200 ms) hasta recibir su {"tipo":"ack","id":N}: una
// pulsacion perdida dejaria al operario esperando.
static bool     ok_tx_activo   = false;
static int      ok_tx_intentos = 0;
static uint32_t ok_tx_ultimo   = 0;
static uint32_t ok_tx_id       = 0;
static uint32_t ok_toque_ms    = 0;

static void ok_tx_iniciar() {
    ok_tx_id       = millis();
    ok_tx_activo   = true;
    ok_tx_intentos = 0;
    ok_tx_ultimo   = 0;            // dispara el primer envio de inmediato
}
static void ok_tx_paso() {
    if (!ok_tx_activo) return;
    uint32_t now = millis();
    if (ok_tx_ultimo && now - ok_tx_ultimo < 200) return;
    if (ok_tx_intentos >= 3) {
        ok_tx_activo = false;
        snprintf(diag, sizeof(diag), "OK tactil sin ACK del carro");
        return;
    }
    char linea[110];
    snprintf(linea, sizeof(linea),
             "{\"v\":1,\"tipo\":\"ok\",\"carro\":\"%s\",\"sel\":\"%s\",\"id\":%lu}\n",
             carro_id, sel_id, (unsigned long)ok_tx_id);
    carroUart.print(linea);
    ok_tx_intentos++;
    ok_tx_ultimo = now;
}

static void ok_anim_opa_cb(void *obj, int32_t v) {
    lv_obj_set_style_bg_opa((lv_obj_t *)obj, v, 0);
}
static void ok_click_cb(lv_event_t *e) {
    (void)e;
#if TOUCH_DEBUG
    dbg_clicks++;
#endif
    uint32_t now = millis();
    if (now - ok_toque_ms < 1500) return;   // antirrebote / doble toque
    ok_toque_ms = now;
    ok_tx_iniciar();
    // "OK" grande y fugaz para que el operario vea que el toque entro
    if (ok_overlay) {
        lv_obj_t *fx = lv_label_create(ok_overlay);
        lv_label_set_text(fx, "OK");
        lv_obj_set_style_text_font(fx, F_XL, 0);
        lv_obj_set_style_text_color(fx, COL_VERDE, 0);
        lv_obj_set_style_bg_color(fx, COL_NEGRO, 0);
        lv_obj_set_style_bg_opa(fx, LV_OPA_70, 0);
        lv_obj_set_style_pad_all(fx, 18, 0);
        lv_obj_set_style_radius(fx, 16, 0);
        lv_obj_center(fx);
        lv_obj_delete_delayed(fx, 700);
    }
}

// Velo transparente que capta el toque en cualquier parte de la pantalla
// cuando el carro pide confirmacion. Se crea sobre la pantalla activa (no
// dentro de 'cont', que lv_obj_clean vacia en cada refresco) y se retira en
// cuanto el carro deja de pedir OK.
static void ok_overlay_quitar() {
    if (ok_overlay) { lv_obj_delete(ok_overlay); ok_overlay = nullptr; }
}
static void ok_overlay_poner() {
    if (ok_overlay) return;
    ok_overlay = lv_obj_create(lv_screen_active());
    lv_obj_remove_style_all(ok_overlay);
    lv_obj_set_size(ok_overlay, LV_W, 340);          // toda la zona inferior = tecla Enter
    lv_obj_set_pos(ok_overlay, 0, LV_H - 340);
    lv_obj_remove_flag(ok_overlay, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(ok_overlay, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(ok_overlay, ok_click_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_move_foreground(ok_overlay);
}

// ── Calibracion tactil: rutina guiada ─────────────────────────────────────
enum { CAL_N = 5 };

// Resuelve un sistema 3x3 (eliminacion de Gauss con pivoteo). true si va bien.
static bool cal_resolver3(double A[3][3], double b[3], double x[3]) {
    double m[3][4];
    for (int r = 0; r < 3; r++) { for (int c = 0; c < 3; c++) m[r][c] = A[r][c]; m[r][3] = b[r]; }
    for (int col = 0; col < 3; col++) {
        int piv = col; double best = fabs(m[col][col]);
        for (int r = col + 1; r < 3; r++) if (fabs(m[r][col]) > best) { best = fabs(m[r][col]); piv = r; }
        if (best < 1e-9) return false;
        if (piv != col) for (int c = 0; c < 4; c++) { double t = m[col][c]; m[col][c] = m[piv][c]; m[piv][c] = t; }
        double d = m[col][col];
        for (int c = col; c < 4; c++) m[col][c] /= d;
        for (int r = 0; r < 3; r++) {
            if (r == col) continue;
            double f = m[r][col];
            for (int c = col; c < 4; c++) m[r][c] -= f * m[col][c];
        }
    }
    x[0] = m[0][3]; x[1] = m[1][3]; x[2] = m[2][3];
    return true;
}

// Pantalla de un punto: cruz + anillo en (tx,ty) e instruccion.
static void cal_pantalla(int idx, int total, int tx, int ty) {
    lv_obj_t *scr = lv_screen_active();
    lv_obj_clean(scr);
    lv_obj_set_style_bg_color(scr, COL_BG, 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    lv_obj_t *h = lv_obj_create(scr);
    lv_obj_remove_style_all(h);
    lv_obj_set_size(h, 90, 6);
    lv_obj_set_style_bg_color(h, COL_VERDE, 0);
    lv_obj_set_style_bg_opa(h, LV_OPA_COVER, 0);
    lv_obj_set_pos(h, tx - 45, ty - 3);

    lv_obj_t *v = lv_obj_create(scr);
    lv_obj_remove_style_all(v);
    lv_obj_set_size(v, 6, 90);
    lv_obj_set_style_bg_color(v, COL_VERDE, 0);
    lv_obj_set_style_bg_opa(v, LV_OPA_COVER, 0);
    lv_obj_set_pos(v, tx - 3, ty - 45);

    lv_obj_t *ring = lv_obj_create(scr);
    lv_obj_remove_style_all(ring);
    lv_obj_set_size(ring, 64, 64);
    lv_obj_set_style_radius(ring, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_border_width(ring, 4, 0);
    lv_obj_set_style_border_color(ring, COL_VERDE, 0);
    lv_obj_set_pos(ring, tx - 32, ty - 32);

    lv_obj_t *t = lv_label_create(scr);
    lv_label_set_text_fmt(t, "CALIBRACION TACTIL\n\nToca el centro de la cruz\n\nPunto %d de %d", idx, total);
    lv_obj_set_style_text_font(t, F_MD, 0);
    lv_obj_set_style_text_color(t, COL_TXT, 0);
    lv_obj_set_style_text_align(t, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(t, LV_ALIGN_CENTER, 0, ty > LV_H / 2 ? -170 : 170);

    lv_refr_now(NULL);
}

// Mensaje a pantalla completa durante 'ms'.
static void cal_aviso(const char *msg, lv_color_t col, uint32_t ms) {
    lv_obj_t *scr = lv_screen_active();
    lv_obj_clean(scr);
    lv_obj_set_style_bg_color(scr, COL_BG, 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_t *t = lv_label_create(scr);
    lv_label_set_text(t, msg);
    lv_obj_set_style_text_font(t, F_MD, 0);
    lv_obj_set_style_text_color(t, col, 0);
    lv_obj_set_style_text_align(t, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_center(t);
    lv_refr_now(NULL);
    uint32_t t0 = millis();
    while (millis() - t0 < ms) { lv_refr_now(NULL); delay(20); }
}

// Espera un toque completo y devuelve el crudo promediado. false si no llega.
static bool cal_leer_punto(int *rawx, int *rawy) {
    int x, y;
    uint32_t t0 = millis();
    while (touch_raw(&x, &y)) {                 // suelta un dedo previo
        if (millis() - t0 > 5000) break;
        delay(10);
    }
    t0 = millis();
    while (!touch_raw(&x, &y)) {                // espera pulsacion
        if (millis() - t0 > 25000) return false;  // tactil sin respuesta
        delay(10);
    }
    long sx = 0, sy = 0; int n = 0;
    uint32_t tp = millis();
    while (millis() - tp < 300) {               // promedia con el dedo abajo
        if (!touch_raw(&x, &y)) break;
        sx += x; sy += y; n++;
        delay(10);
    }
    if (n < 2) return false;
    *rawx = (int)(sx / n);
    *rawy = (int)(sy / n);
    t0 = millis();
    while (touch_raw(&x, &y)) {                 // espera liberacion
        if (millis() - t0 > 5000) break;
        delay(10);
    }
    return true;
}

static void cal_cargar() {
    prefs.begin("p4touch", true);
    cal_valida = prefs.getBool("ok", false);
    if (cal_valida) {
        cal_ax = prefs.getDouble("ax", 1); cal_bx = prefs.getDouble("bx", 0); cal_cx = prefs.getDouble("cx", 0);
        cal_ay = prefs.getDouble("ay", 0); cal_by = prefs.getDouble("by", 1); cal_cy = prefs.getDouble("cy", 0);
    }
    prefs.end();
    Serial.printf("cal: %s  ax=%.5f bx=%.5f cx=%.2f  ay=%.5f by=%.5f cy=%.2f\n",
                  cal_valida ? "cargada de NVS" : "SIN calibrar",
                  cal_ax, cal_bx, cal_cx, cal_ay, cal_by, cal_cy);
}

static void cal_guardar() {
    prefs.begin("p4touch", false);
    prefs.putDouble("ax", cal_ax); prefs.putDouble("bx", cal_bx); prefs.putDouble("cx", cal_cx);
    prefs.putDouble("ay", cal_ay); prefs.putDouble("by", cal_by); prefs.putDouble("cy", cal_cy);
    prefs.putBool("ok", true);
    prefs.end();
    cal_valida = true;
}

// Ventana breve al arrancar (solo si ya habia calibracion) para repetirla.
static bool cal_pedir_recalibrado(uint32_t ms) {
    lv_obj_t *scr = lv_screen_active();
    lv_obj_clean(scr);
    lv_obj_set_style_bg_color(scr, COL_BG, 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_t *t = lv_label_create(scr);
    lv_obj_set_style_text_font(t, F_MD, 0);
    lv_obj_set_style_text_color(t, COL_MUTE, 0);
    lv_obj_set_style_text_align(t, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_center(t);
    uint32_t t0 = millis();
    bool tocado = false;
    int x, y;
    while (millis() - t0 < ms) {
        if (touch_raw(&x, &y)) { tocado = true; break; }
        lv_label_set_text_fmt(t, "Tactil calibrado.\n\nToca la pantalla ahora para\nrepetir la calibracion   (%lu)",
                              (unsigned long)((ms - (millis() - t0)) / 1000 + 1));
        lv_refr_now(NULL);
        delay(15);
    }
    if (tocado) {
        uint32_t r0 = millis();
        while (touch_raw(&x, &y)) { if (millis() - r0 > 4000) break; delay(10); }
    }
    lv_obj_clean(scr);
    return tocado;
}

// Rutina completa: 5 cruces -> ajuste afin por minimos cuadrados -> NVS.
static void calibrar() {
    const int TX[CAL_N] = { 120, LV_W - 120, LV_W - 120, 120, LV_W / 2 };
    const int TY[CAL_N] = { 120, 120, LV_H - 120, LV_H - 120, LV_H / 2 };
    int rx[CAL_N], ry[CAL_N], gx[CAL_N], gy[CAL_N], got = 0;

    for (int i = 0; i < CAL_N; i++) {
        cal_pantalla(i + 1, CAL_N, TX[i], TY[i]);
        int a, b;
        if (cal_leer_punto(&a, &b)) {
            rx[got] = a; ry[got] = b; gx[got] = TX[i]; gy[got] = TY[i]; got++;
            Serial.printf("cal p%d  target=(%d,%d)  raw=(%d,%d)\n", i + 1, TX[i], TY[i], a, b);
            lv_obj_t *ok = lv_label_create(lv_screen_active());
            lv_label_set_text(ok, "OK");
            lv_obj_set_style_text_font(ok, F_XL, 0);
            lv_obj_set_style_text_color(ok, COL_VERDE, 0);
            lv_obj_center(ok);
            lv_refr_now(NULL);
            delay(300);
        } else {
            Serial.printf("cal p%d  SIN toque (timeout)\n", i + 1);
        }
    }

    if (got < 3) {
        char m[128];
        snprintf(m, sizeof(m), "Tactil sin respuesta.\n\nGT911 I2C: %s\n\nSe mantiene el mapa anterior.", cal_i2c);
        cal_aviso(m, COL_ROJO, 4000);
        lv_obj_clean(lv_screen_active());
        return;
    }

    double Sxx = 0, Sxy = 0, Sx = 0, Syy = 0, Sy = 0;
    double bx0 = 0, bx1 = 0, bx2 = 0, by0 = 0, by1 = 0, by2 = 0;
    for (int k = 0; k < got; k++) {
        double X = rx[k], Y = ry[k];
        Sxx += X * X; Sxy += X * Y; Sx += X; Syy += Y * Y; Sy += Y;
        bx0 += X * gx[k]; bx1 += Y * gx[k]; bx2 += gx[k];
        by0 += X * gy[k]; by1 += Y * gy[k]; by2 += gy[k];
    }
    double A[3][3] = { { Sxx, Sxy, Sx }, { Sxy, Syy, Sy }, { Sx, Sy, (double)got } };
    double cx[3], cy[3], bxv[3] = { bx0, bx1, bx2 }, byv[3] = { by0, by1, by2 };
    if (!cal_resolver3(A, bxv, cx) || !cal_resolver3(A, byv, cy)) {
        cal_aviso("No se pudo calcular.\n\nSe mantiene el mapa anterior.", COL_ROJO, 3000);
        lv_obj_clean(lv_screen_active());
        return;
    }

    double err = 0;
    for (int k = 0; k < got; k++) {
        double px = cx[0] * rx[k] + cx[1] * ry[k] + cx[2];
        double py = cy[0] * rx[k] + cy[1] * ry[k] + cy[2];
        err += (px - gx[k]) * (px - gx[k]) + (py - gy[k]) * (py - gy[k]);
    }
    err = sqrt(err / got);

    cal_ax = cx[0]; cal_bx = cx[1]; cal_cx = cx[2];
    cal_ay = cy[0]; cal_by = cy[1]; cal_cy = cy[2];
    cal_guardar();
    Serial.printf("cal OK  rms=%.1fpx  ax=%.5f bx=%.5f cx=%.2f  ay=%.5f by=%.5f cy=%.2f\n",
                  err, cal_ax, cal_bx, cal_cx, cal_ay, cal_by, cal_cy);

    char m[128];
    snprintf(m, sizeof(m), "Calibracion guardada.\n\nError medio: %d px\n\nArrancando el panel...", (int)lround(err));
    cal_aviso(m, err < 45 ? COL_VERDE : COL_AMBAR, 2600);
    lv_obj_clean(lv_screen_active());
}

// ── Vistas ─────────────────────────────────────────────────────────────────
static lv_obj_t *panelCentral(const char *titulo) {
    lv_obj_t *c = card(cont, COL_LINE);
    lv_obj_set_height(c, LV_PCT(100));
    lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(c, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    txt(c, titulo, F_LG, COL_MUTE);
    return c;
}

static void ui_espera() {
    lv_obj_clean(cont);
    lv_obj_t *c = panelCentral("Esperando al carro");
    txt(c, "UART1  rx=52  tx=50  115200", F_MD, COL_MUTE);
}

static void ui_diag() {
    lv_obj_clean(cont);
    lv_obj_t *c = card(cont, COL_ROJO);
    lv_obj_set_height(c, LV_PCT(100));
    lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_gap(c, 10, 0);
    txt(c, "Llegan bytes pero no son una trama valida", F_LG, COL_ROJO);
    lv_obj_t *l1 = lv_label_create(c);
    lv_label_set_text_fmt(l1, "UART1 rx=52 tx=50  115200   |   %lu B recibidos   |   buf %d B",
                          rx_bytes, buf.length());
    lv_obj_set_style_text_font(l1, F_SM, 0); lv_obj_set_style_text_color(l1, COL_TXT, 0);
    lv_obj_t *l2 = lv_label_create(c);
    lv_label_set_text_fmt(l2, "ultimo parseo:  %s", diag);
    lv_obj_set_style_text_font(l2, F_SM, 0); lv_obj_set_style_text_color(l2, COL_TXT, 0);
    txt(c, "ultima linea recibida:", F_SM, COL_MUTE);
    lv_obj_t *raw = lv_label_create(c);
    lv_label_set_text(raw, lastline[0] ? lastline : "(vacia)");
    lv_obj_set_width(raw, LV_PCT(100));
    lv_label_set_long_mode(raw, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_font(raw, F_XS, 0);
    lv_obj_set_style_text_color(raw, COL_TXT, 0);
}

static void ui_lista(bool aviso_sel) {
    lv_obj_clean(cont);
    if (aviso_sel) {
        lv_obj_t *a = card(cont, COL_MUTE);
        txt(a, "El puesto identificado no tiene paquetes en este carro", F_SM, COL_MUTE);
    }
    if (nops == 0) { panelCentral("Sin trabajo en el carro"); return; }

    int vis = nops < MAX_ROWS ? nops : MAX_ROWS;
    for (int i = 0; i < vis; i++) {
        const Op &o = ops_buf[i];
        lv_color_t cf = colorFase(o.fase);
        lv_obj_t *row = card(cont, cf);
        lv_obj_set_height(row, 84);
        lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(row, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        lv_obj_set_style_pad_column(row, 16, 0);

        if (o.boton > 0) {
            char b[4]; snprintf(b, sizeof(b), "%d", o.boton);
            lv_obj_t *badge = chip(row, b, cf, F_MD);
            lv_obj_set_style_pad_hor(badge, 20, 0);
        } else {
            lv_obj_t *dot = lv_obj_create(row);
            lv_obj_set_size(dot, 24, 24);
            lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
            lv_obj_set_style_bg_color(dot, cf, 0);
            lv_obj_set_style_border_width(dot, 0, 0);
        }
        lv_obj_t *nm = txt(row, o.puesto[0] ? o.puesto : "(sin nombre)", F_MD, COL_TXT);
        lv_obj_set_flex_grow(nm, 1);
        lv_obj_t *np = lv_label_create(row);
        lv_label_set_text_fmt(np, "%d paq", o.npaq);
        lv_obj_set_style_text_font(np, F_SM, 0);
        lv_obj_set_style_text_color(np, COL_MUTE, 0);
        chip(row, labelFase(o.fase), cf, F_XS);
    }
}

// Una celda del grid de paquetes: el fondo es el color de la etiqueta (el mismo
// que pinta el modal del SW web), con el numero de etiqueta enorme, el nombre
// del elemento debajo y los contadores cables / term. en pequeno.
static void celdaPaquete(lv_obj_t *parent, const Paq &p, int cw, int ch) {
    lv_color_t bg = p.bloq ? lv_color_hex(0x39414F) : lv_color_hex(p.rgb);
    lv_color_t tc = p.bloq ? COL_MUTE               : lv_color_hex(p.trgb);

    lv_obj_t *cell = lv_obj_create(parent);
    lv_obj_set_size(cell, cw, ch);
    lv_obj_set_style_bg_color(cell, bg, 0);
    lv_obj_set_style_bg_opa(cell, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(cell, 18, 0);
    lv_obj_set_style_border_width(cell, p.bloq ? 2 : 0, 0);
    lv_obj_set_style_border_color(cell, COL_ROJO, 0);
    lv_obj_set_style_shadow_width(cell, 16, 0);
    lv_obj_set_style_shadow_opa(cell, LV_OPA_30, 0);
    lv_obj_set_style_shadow_color(cell, lv_color_black(), 0);
    lv_obj_set_style_shadow_offset_y(cell, 4, 0);
    lv_obj_set_style_pad_hor(cell, 12, 0);
    lv_obj_set_style_pad_ver(cell, 8, 0);
    lv_obj_set_style_pad_gap(cell, 0, 0);
    lv_obj_set_flex_flow(cell, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(cell, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_remove_flag(cell, LV_OBJ_FLAG_SCROLLABLE);

    // Nombre del elemento arriba
    lv_obj_t *e = lv_label_create(cell);
    lv_label_set_text(e, p.bloq ? "EN USO" : (p.elem[0] ? p.elem : "(sin nombre)"));
    lv_obj_set_style_text_font(e, F_LG, 0);
    lv_obj_set_style_text_color(e, tc, 0);
    lv_obj_set_width(e, LV_PCT(100));
    lv_label_set_long_mode(e, LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_align(e, LV_TEXT_ALIGN_CENTER, 0);

    // Nº de etiqueta flotando en el centro (SPACE_BETWEEN lo deja centrado
    // entre el nombre y los contadores), enorme
    lv_obj_t *n = lv_label_create(cell);
    lv_label_set_text(n, p.etiqueta[0] ? p.etiqueta : "-");
    lv_obj_set_style_text_font(n, F_HUGE, 0);
    lv_obj_set_style_text_color(n, tc, 0);
    lv_obj_set_width(n, LV_PCT(100));
    lv_obj_set_style_text_align(n, LV_TEXT_ALIGN_CENTER, 0);

    // Contadores abajo
    lv_obj_t *m = lv_label_create(cell);
    lv_label_set_text_fmt(m, "%d cbl   ·   %d term", p.cables, p.term);
    lv_obj_set_style_text_font(m, F_SM, 0);
    lv_obj_set_style_text_color(m, tc, 0);
    lv_obj_set_style_text_opa(m, LV_OPA_70, 0);
}

static void ui_detalle(int idx) {
    lv_obj_clean(cont);
    const Op &o = ops_buf[idx];
    lv_color_t cf = colorFase(o.fase);

    lv_obj_t *c = card(cont, cf);
    lv_obj_set_height(c, LV_PCT(100));
    lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_gap(c, 10, 0);

    // Cabecera de la tarjeta: puesto + fase
    lv_obj_t *head = lv_obj_create(c);
    lv_obj_set_width(head, LV_PCT(100));
    lv_obj_set_height(head, LV_SIZE_CONTENT);
    lv_obj_set_style_bg_opa(head, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(head, 0, 0);
    lv_obj_set_style_pad_all(head, 0, 0);
    lv_obj_set_flex_flow(head, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(head, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_remove_flag(head, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *nm = txt(head, o.puesto[0] ? o.puesto : "(sin nombre)", F_LG, COL_TXT);
    lv_obj_set_flex_grow(nm, 1);
    chip(head, labelFase(o.fase), cf, F_MD);

    lv_obj_t *meta = lv_label_create(c);
    if (o.grupos > 1 && o.lote[0])
        lv_label_set_text_fmt(meta, "Grupo %d de %d   ·   %d paquetes   ·   Lote %s",
                              o.grupo, o.grupos, o.npaq, o.lote);
    else if (o.grupos > 1)
        lv_label_set_text_fmt(meta, "Grupo %d de %d   ·   %d paquetes", o.grupo, o.grupos, o.npaq);
    else if (o.lote[0])
        lv_label_set_text_fmt(meta, "%d paquetes   ·   Lote %s", o.npaq, o.lote);
    else
        lv_label_set_text_fmt(meta, "%d paquetes", o.npaq);
    lv_obj_set_style_text_font(meta, F_SM, 0);
    lv_obj_set_style_text_color(meta, COL_MUTE, 0);

    // Grid de paquetes: fila con wrap -> 3 celdas arriba, 2 abajo (centradas).
    lv_obj_t *grid = lv_obj_create(c);
    lv_obj_set_width(grid, LV_PCT(100));
    lv_obj_set_flex_grow(grid, 1);
    lv_obj_set_style_bg_opa(grid, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(grid, 0, 0);
    lv_obj_set_style_pad_all(grid, 0, 0);
    lv_obj_set_style_pad_column(grid, 16, 0);
    lv_obj_set_style_pad_row(grid, 16, 0);
    lv_obj_set_flex_flow(grid, LV_FLEX_FLOW_ROW_WRAP);
    lv_obj_set_flex_align(grid, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_scrollbar_mode(grid, LV_SCROLLBAR_MODE_OFF);

    if (o.nbuf <= 0) {
        txt(grid, "Sin paquetes", F_LG, COL_MUTE);
    } else {
        // 3 celdas por fila, 2 filas. Descuento paddings de cont (40) y card (32).
        int gw = LV_W - 40 - 32;
        int gh = LV_H - 100 - 40 - 32 - 64 - 28 - 30;   // header, pads, cabecera, meta, gaps
        if (pide_ok) gh -= 106;                         // hueco de la barra CONFIRMAR
        int cw = (gw - 2 * 16 - 6) / 3;                 // -6: margen para que quepan 3
        int ch = (gh - 16) / 2;
        if (ch < 150) ch = 150;
        if (ch > 300) ch = 300;
        for (int t = 0; t < o.nbuf; t++) celdaPaquete(grid, o.paq[t], cw, ch);
    }

    // Barra CONFIRMAR: solo cuando el carro la pide. Parpadea para que se vea
    // desde lejos; al tocarla se manda el OK al carro (con ACK y reintento).
    if (!pide_ok) return;
    lv_obj_t *ok = lv_obj_create(c);
    lv_obj_set_width(ok, LV_PCT(100));
    lv_obj_set_height(ok, 96);
    lv_obj_set_style_bg_color(ok, COL_VERDE, 0);
    lv_obj_set_style_bg_opa(ok, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(ok, 18, 0);
    lv_obj_set_style_border_width(ok, 0, 0);
    lv_obj_set_style_shadow_width(ok, 20, 0);
    lv_obj_set_style_shadow_opa(ok, LV_OPA_40, 0);
    lv_obj_set_style_shadow_color(ok, lv_color_black(), 0);
    lv_obj_remove_flag(ok, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(ok, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(ok, ok_click_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *okt = lv_label_create(ok);
    lv_label_set_text(okt, "CONFIRMAR");
    lv_obj_set_style_text_font(okt, F_XL, 0);
    lv_obj_set_style_text_color(okt, COL_NEGRO, 0);
    lv_obj_center(okt);

    lv_anim_t an;
    lv_anim_init(&an);
    lv_anim_set_var(&an, ok);
    lv_anim_set_exec_cb(&an, ok_anim_opa_cb);
    lv_anim_set_values(&an, LV_OPA_40, LV_OPA_COVER);
    lv_anim_set_duration(&an, 450);
    lv_anim_set_playback_duration(&an, 450);
    lv_anim_set_repeat_count(&an, LV_ANIM_REPEAT_INFINITE);
    lv_anim_start(&an);
}

static void ui_actualizar(bool forzar) {
    uint32_t h = huellaActual();
    if (!forzar && h == huella_prev) return;
    huella_prev = h;

    lv_label_set_text_fmt(lbl_carro, "CARRO %s", carro_id);
    lv_label_set_text(lbl_wifi, wifi_ok ? "WiFi" : "SIN WiFi");
    lv_obj_set_style_text_color(lbl_wifi, wifi_ok ? COL_VERDE : COL_ROJO, 0);
    lv_label_set_text_fmt(lbl_fw, "fw %s", fw_buf);

    if (!tiene_datos && rx_bytes == 0)      ui_espera();
    else if (!tiene_datos)                  ui_diag();
    else {
        int si = selIndex();
        if (si >= 0) ui_detalle(si);
        else         ui_lista(sel_id[0] != '\0');
    }

    // El velo de confirmacion solo vive mientras haya detalle y el carro pida OK.
    if (tiene_datos && selIndex() >= 0 && pide_ok) ok_overlay_poner();
    else                                           ok_overlay_quitar();
}

// ── LVGL: pintar / tactil / tick ───────────────────────────────────────────
// El framebuffer del panel es vertical (800x1280). La UI es apaisada
// (1280x800). Se rota 90 CW al volcar: nx = (NAT_W-1) - ly ; ny = lx.
static void flush_cb(lv_display_t *d, const lv_area_t *a, uint8_t *px) {
    const uint16_t *src = (const uint16_t *)px;
    uint16_t *dst = (uint16_t *)fb;
    for (int ly = a->y1; ly <= a->y2; ly++) {
        int nx = (NAT_W - 1) - ly;
        if (nx < 0 || nx >= NAT_W) { src += (a->x2 - a->x1 + 1); continue; }
        for (int lx = a->x1; lx <= a->x2; lx++) {
            if (lx >= 0 && lx < NAT_H) dst[(uint32_t)lx * NAT_W + nx] = *src;
            src++;
        }
    }
    // El framebuffer DPI vive en PSRAM y lo lee por DMA el controlador MIPI-DSI.
    // Si la cache de la CPU no se vuelca a memoria, el DSI ve filas a medio
    // escribir -> "rayas negras" del ancho de una linea de cache (64 B = 32 px).
    // La libreria GFX4d hace este mismo msync tras cada dibujo (EndWrite()); al
    // pintar nosotros directos en 'fb' hay que hacerlo aqui. Las columnas LVGL
    // (a->x1..a->x2) son filas nativas; se vuelca ese rango entero de filas.
    int r0 = a->x1 < 0 ? 0 : a->x1;
    int r1 = a->x2 >= NAT_H ? NAT_H - 1 : a->x2;
    if (fb && r1 >= r0)
        esp_cache_msync(fb + (size_t)r0 * NAT_W * 2,
                        (size_t)(r1 - r0 + 1) * NAT_W * 2,
                        ESP_CACHE_MSYNC_FLAG_DIR_C2M | ESP_CACHE_MSYNC_FLAG_UNALIGNED);
    lv_display_flush_ready(d);
}

static void touch_cb(lv_indev_t *i, lv_indev_data_t *data) {
    int nx, ny;
    if (touch_raw(&nx, &ny)) {
        int lx, ly;
        if (cal_valida) {
            lx = (int)lround(cal_ax * nx + cal_bx * ny + cal_cx);
            ly = (int)lround(cal_ay * nx + cal_by * ny + cal_cy);
        } else {                        // sin calibrar: crudo tal cual
            lx = nx;
            ly = ny;
        }
        // Se recorta para que LVGL siempre situe el punto dentro de la pantalla.
        if (lx < 0) lx = 0; else if (lx >= LV_W) lx = LV_W - 1;
        if (ly < 0) ly = 0; else if (ly >= LV_H) ly = LV_H - 1;
        data->point.x = lx;
        data->point.y = ly;
        data->state = LV_INDEV_STATE_PRESSED;
#if TOUCH_DEBUG
        if (dbg_pen == 0)
            Serial.printf("TOUCH raw=(%d,%d) map=(%d,%d)\n", nx, ny, lx, ly);
        dbg_pen = 1; dbg_rawx = nx; dbg_rawy = ny; dbg_mapx = lx; dbg_mapy = ly;
        dbg_ms = millis();
#endif
    } else {
        data->state = LV_INDEV_STATE_RELEASED;
#if TOUCH_DEBUG
        dbg_pen = 0;
#endif
    }
}

static uint32_t tick_cb(void) { return millis(); }

// ── Parser JSON ────────────────────────────────────────────────────────────
static void procesarLinea(const String &msg) {
    Serial.print("RX ("); Serial.print(msg.length()); Serial.print("): ");
    Serial.println(msg.substring(0, 140));

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, msg.c_str(), msg.length());
    if (err) {
        const char *p = msg.c_str(); int len = msg.length();
        for (int b = 1; b < len && b < 400 && err; b++) {
            if (p[b] != '{') continue;
            DeserializationError e2 = deserializeJson(doc, p + b, len - b);
            if (!e2) { err = e2; Serial.printf("recuperado tras %d bytes de ruido\n", b); }
        }
    }
    if (err) {
        snprintf(diag, sizeof(diag), "JSON err: %s", err.c_str());
        Serial.print("JSON err: "); Serial.println(err.c_str());
        if (!tiene_datos) ui_actualizar(false);
        return;
    }

    const char *tipo = doc["tipo"] | "";
    if (!strcmp(tipo, "ack")) {
        uint32_t id = doc["id"] | 0u;
        if (ok_tx_activo && id == ok_tx_id) {
            ok_tx_activo = false;
            snprintf(diag, sizeof(diag), "OK confirmado por el carro");
        }
        return;
    }
    if (strcmp(tipo, "estado") != 0) {
        snprintf(diag, sizeof(diag), "tipo '%s' ignorado", tipo);
        if (!tiene_datos) ui_actualizar(false);
        return;
    }

    copiaCampo(carro_id, sizeof(carro_id), doc["carro"], "--");
    copiaCampo(fw_buf,   sizeof(fw_buf),   doc["fw"],    "---");
    copiaCampo(sel_id,   sizeof(sel_id),   doc["sel"],   "");
    wifi_ok = doc["wifi"] | false;
    pide_ok = doc["ok"]   | false;
    // El carro ya no pide OK (o cambio de puesto): corta cualquier reintento vivo.
    if (!pide_ok) ok_tx_activo = false;

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
        d.boton  = data["boton"]  | 0;
        d.grupo  = data["grupo"]  | 0;
        d.grupos = data["grupos"] | 0;

        JsonArray paq = data["paquetes"].as<JsonArray>();
        d.npaq = paq.size();
        d.nbuf = 0;
        for (JsonObject p : paq) {
            if (d.nbuf >= MAX_TILE) break;
            Paq &q = d.paq[d.nbuf];
            copiaCampo(q.etiqueta, sizeof(q.etiqueta), p["etiqueta"], "-");
            copiaCampo(q.elem,     sizeof(q.elem),     p["elem"],     "");
            copiaCampo(q.cod,      sizeof(q.cod),      p["cod"],      "");
            q.cables = p["cables"] | 0;
            q.term   = p["term"]   | 0;
            q.bloq   = p["bloqueado"] | false;
            q.rgb    = parseHexColor(p["color"],  0x2B3550);
            q.trgb   = parseHexColor(p["tcolor"], 0xF4F7FB);
            d.nbuf++;
        }
        nops++;
    }

    snprintf(diag, sizeof(diag), "OK %d puesto%s%s", nops, nops == 1 ? "" : "s",
             sel_id[0] ? " (detalle)" : "");
    tiene_datos = true;
    ultimo_rx   = millis();
    ui_actualizar(false);
}

// ── Construccion de la UI fija (cabecera + contenedor) ──────────────────────
static void ui_build() {
    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, COL_BG, 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(scr, 0, 0);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *head = lv_obj_create(scr);
    lv_obj_set_size(head, LV_W, 100);          // llega justo a 'cont' (y=100): sin franja negra en la costura
    lv_obj_set_pos(head, 0, 0);
    lv_obj_set_style_bg_color(head, COL_BG, 0);
    lv_obj_set_style_bg_opa(head, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(head, 0, 0);
    lv_obj_set_style_border_width(head, 0, 0);
    lv_obj_set_style_border_side(head, LV_BORDER_SIDE_BOTTOM, 0);
    lv_obj_set_style_border_color(head, COL_LINE, 0);
    lv_obj_set_style_border_width(head, 2, 0);
    lv_obj_set_style_pad_all(head, 0, 0);
    lv_obj_remove_flag(head, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *marca = txt(head, "COJO", F_LG, COL_TXT);
    lv_obj_align(marca, LV_ALIGN_TOP_LEFT, 20, 10);
    lv_obj_t *sw = txt(head, "sw", F_SM, COL_MUTE);
    lv_obj_align_to(sw, marca, LV_ALIGN_OUT_RIGHT_BOTTOM, 6, -6);
    lv_obj_t *eng = txt(head, "ENGASTADO", F_XS, COL_AMBAR);
    lv_obj_align(eng, LV_ALIGN_TOP_LEFT, 22, 58);

    lbl_carro = txt(head, "CARRO --", F_LG, COL_TXT);
    lv_obj_align(lbl_carro, LV_ALIGN_TOP_MID, 0, 22);

    lbl_wifi = txt(head, "SIN WiFi", F_SM, COL_ROJO);
    lv_obj_align(lbl_wifi, LV_ALIGN_TOP_RIGHT, -20, 16);
    lbl_fw = txt(head, "fw ---", F_XS, COL_MUTE);
    lv_obj_align(lbl_fw, LV_ALIGN_TOP_RIGHT, -20, 52);

    cont = lv_obj_create(scr);
    lv_obj_set_size(cont, LV_W, LV_H - 100);
    lv_obj_set_pos(cont, 0, 100);
    lv_obj_set_style_bg_opa(cont, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(cont, 0, 0);
    lv_obj_set_style_pad_all(cont, 20, 0);
    lv_obj_set_style_pad_row(cont, 12, 0);
    lv_obj_set_flex_flow(cont, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_scrollbar_mode(cont, LV_SCROLLBAR_MODE_OFF);

#if TOUCH_DEBUG
    lbl_dbg = lv_label_create(scr);
    lv_label_set_text(lbl_dbg, "touch: sin toque");
    lv_obj_set_style_text_font(lbl_dbg, F_XS, 0);
    lv_obj_set_style_text_color(lbl_dbg, COL_AMBAR, 0);
    lv_obj_set_style_bg_color(lbl_dbg, COL_NEGRO, 0);
    lv_obj_set_style_bg_opa(lbl_dbg, LV_OPA_50, 0);
    lv_obj_set_style_pad_hor(lbl_dbg, 6, 0);
    lv_obj_align(lbl_dbg, LV_ALIGN_BOTTOM_LEFT, 6, -6);
#endif
}

// ── Setup / loop ───────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    gfx.begin();
    gfx.BacklightOn(true);
    gfx.touch_Set(TOUCH_ENABLE);
    fb = gfx.SelectFB(0);

    // Sonda I2C del GT911 (bus 7/8, lo abrio gfx.begin()). Deja constancia en
    // pantalla si la calibracion no recibe toques: distingue "sin cablear /
    // sin masa" de "coordenadas raras".
    {
        Wire.beginTransmission(0x5D); int e5d = Wire.endTransmission();
        Wire.beginTransmission(0x14); int e14 = Wire.endTransmission();
        snprintf(cal_i2c, sizeof(cal_i2c), "0x5D=%s 0x14=%s",
                 e5d == 0 ? "OK" : "no", e14 == 0 ? "OK" : "no");
        Serial.printf("GT911 %s\n", cal_i2c);
    }

    // Pinta el framebuffer entero del color de fondo antes de arrancar LVGL.
    // En modo PARTIAL, LVGL solo repinta lo que cambia; si algun borde no lo
    // toca nunca, se queda con este color (tema oscuro) en vez de negro
    // -> se acaban las "rayas negras" en los bordes de la pantalla.
    if (fb) {
        const uint16_t bg565 = ((0x0B >> 3) << 11) | ((0x0F >> 2) << 5) | (0x17 >> 3);
        uint16_t *pfb = (uint16_t *)fb;
        for (uint32_t i = 0; i < (uint32_t)NAT_W * NAT_H; i++) pfb[i] = bg565;
        esp_cache_msync(fb, (size_t)NAT_W * NAT_H * 2,
                        ESP_CACHE_MSYNC_FLAG_DIR_C2M | ESP_CACHE_MSYNC_FLAG_UNALIGNED);
    }

    buf.reserve(2048);
    carroUart.setRxBufferSize(4096);
    carroUart.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);

    lv_init();
    lv_tick_set_cb(tick_cb);

    static size_t BUFPX = LV_W * 240;
    void *b1 = heap_caps_malloc(BUFPX * 2, MALLOC_CAP_SPIRAM);
    void *b2 = heap_caps_malloc(BUFPX * 2, MALLOC_CAP_SPIRAM);
    if (!b1 || !b2) { Serial.println("SIN PSRAM para los buffers LVGL"); }

    // La UI es apaisada; la rotacion al framebuffer vertical la hace flush_cb.
    lv_display_t *disp = lv_display_create(LV_W, LV_H);
    lv_display_set_flush_cb(disp, flush_cb);
    lv_display_set_buffers(disp, b1, b2, BUFPX * 2, LV_DISPLAY_RENDER_MODE_PARTIAL);

    lv_indev_t *indev = lv_indev_create();
    lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(indev, touch_cb);
    lv_indev_set_display(indev, disp);

    // Calibracion tactil: obligatoria la primera vez; despues, una ventana de
    // 2,5 s al arrancar para repetirla. Va antes de construir la UI porque usa
    // la pantalla activa como lienzo.
    cal_cargar();
    if (!cal_valida || cal_pedir_recalibrado(2500))
        calibrar();

    ui_build();
    ui_actualizar(true);
    lv_obj_invalidate(lv_screen_active());   // repinta TODA la pantalla al menos una vez

    Serial.println("P4 pantalla_p4_101 v12 (LVGL) ready");
    Serial.printf("UART1 rx=%d tx=%d baud=%lu rxbuf=4096\n", UART_RX_PIN, UART_TX_PIN,
                  (unsigned long)UART_BAUD);
}

void loop() {
    pump();
    ok_tx_paso();
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
        ui_actualizar(true);
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
    }

#if TOUCH_DEBUG
    static uint32_t dbg_lbl_ms = 0;
    if (lbl_dbg && now - dbg_lbl_ms > 150) {
        dbg_lbl_ms = now;
        lv_label_set_text_fmt(lbl_dbg,
            "cal=%d  touch pen=%d raw(%d,%d) map(%d,%d) clk=%lu age=%lums ovl=%d",
            cal_valida ? 1 : 0, dbg_pen, dbg_rawx, dbg_rawy, dbg_mapx, dbg_mapy,
            (unsigned long)dbg_clicks,
            (unsigned long)(dbg_ms ? now - dbg_ms : 0),
            ok_overlay ? 1 : 0);
    }
#endif

    lv_timer_handler();
    delay(4);
}
