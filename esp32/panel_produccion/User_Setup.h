// ============================================================
//  User_Setup.h para 4D Systems gen4-ESP32-24 (ILI9341, SPI)
// ============================================================
//
// ⚠ CÓMO USAR:
//   1. Instala la librería TFT_eSPI desde el Gestor de librerías
//   2. Abre el explorador de archivos y ve a:
//      C:\Users\<usuario>\Documents\Arduino\libraries\TFT_eSPI\
//   3. Renombra el User_Setup.h que ya existe a User_Setup.h.bak
//   4. Copia ESTE archivo al mismo sitio con el nombre User_Setup.h
//
// ⚠ PINES — Verifica con el datasheet de tu placa:
//   https://4dsystems.com.au/products/gen4-esp32-24/
//   Busca "gen4-ESP32 Arduino Getting Started" (AN-P6001) en su web.
//
// Los valores abajo son los más comunes para el gen4-ESP32-24.
// Si la pantalla sale en blanco o con colores incorrectos, ajusta
// TFT_DC y TFT_RST con los pines reales del esquemático.
// ============================================================

// --- Driver ---
#define ILI9341_DRIVER

// --- Resolución ---
#define TFT_WIDTH  240
#define TFT_HEIGHT 320

// --- Pines SPI (ESP32 VSPI estándar) ---
#define TFT_MOSI  23    // SPI MOSI  — confirmar con esquemático
#define TFT_SCLK  18    // SPI CLK   — confirmar con esquemático
#define TFT_CS     5    // Chip Select
#define TFT_DC    21    // Data/Command (A0)  ← revisar, puede ser 2 ó 27
#define TFT_RST   22    // Reset              ← revisar, puede ser 4 ó 33
// #define TFT_MISO 19  // No necesario si solo escribes en pantalla

// --- Retroiluminación (pin en alta = encendido) ---
// #define TFT_BL   15    // Descomenta si tu placa necesita controlar el backlight

// --- Velocidad SPI ---
#define SPI_FREQUENCY       40000000   // 40 MHz (bajar a 27MHz si hay glitches)
#define SPI_READ_FREQUENCY   20000000

// --- Fuente integrada ---
#define LOAD_GLCD    // Fuente 5x7 (la usamos para texto pequeño)
#define LOAD_FONT2   // Fuente 16px
#define LOAD_FONT4   // Fuente 26px
#define LOAD_FONT6   // Fuente 48px — solo dígitos
#define LOAD_GFXFF   // FreeFonts
#define SMOOTH_FONT
