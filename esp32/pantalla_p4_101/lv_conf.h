/*
 * lv_conf.h  —  configuracion de LVGL 9.x para el panel del carro (ESP32-P4).
 *
 * Se selecciona con -DLV_CONF_INCLUDE_SIMPLE (ver build_opt.h). Lo que no se
 * fija aqui lo rellena lv_conf_internal.h con los valores por defecto.
 *
 * La libreria LVGL se instala aparte, una sola vez:
 *     arduino-cli lib install lvgl        (o Gestor de Librerias -> "lvgl")
 */
#ifndef LV_CONF_H
#define LV_CONF_H

/* Ojo: nada de #include aqui fuera de un guard __ASSEMBLY__. Este fichero lo
 * arrastra lv_blend_helium.S y el ensamblador de RISC-V no sabe leer C. */

/* ── Color ───────────────────────────────────────────────────────────────── */
#define LV_COLOR_DEPTH   16
#define LV_COLOR_16_SWAP  0        /* el framebuffer del panel es little-endian */

/* ── Memoria ─────────────────────────────────────────────────────────────── */
/* Objetos: malloc del sistema (heap interno). Los buffers grandes de dibujo
 * se reservan a mano en PSRAM y se pasan a lv_display_set_buffers(). */
#define LV_USE_STDLIB_MALLOC    LV_STDLIB_CLIB
#define LV_USE_STDLIB_STRING    LV_STDLIB_CLIB
#define LV_USE_STDLIB_SPRINTF   LV_STDLIB_CLIB

/* ── Dibujo ──────────────────────────────────────────────────────────────── */
#define LV_USE_DRAW_SW        1
#define LV_DRAW_SW_COMPLEX     1   /* sombras, degradados, esquinas redondeadas */
#define LV_DPI_DEF          150

/* ── Sistema operativo / tick ────────────────────────────────────────────── */
#define LV_USE_OS   LV_OS_NONE
/* El tick se da con lv_tick_set_cb(millis) desde el sketch. */

/* ── Log (por printf -> consola serie; ayuda a depurar a ciegas) ─────────── */
#define LV_USE_LOG        1
#define LV_LOG_PRINTF     1
#define LV_LOG_LEVEL      LV_LOG_LEVEL_WARN

/* ── Tipos de letra suavizados (vienen con LVGL) ────────────────────────── */
#define LV_FONT_MONTSERRAT_14  1
#define LV_FONT_MONTSERRAT_16  1
#define LV_FONT_MONTSERRAT_18  1
#define LV_FONT_MONTSERRAT_20  1
#define LV_FONT_MONTSERRAT_24  1
#define LV_FONT_MONTSERRAT_28  1
#define LV_FONT_MONTSERRAT_36  1
#define LV_FONT_MONTSERRAT_48  1
#define LV_FONT_DEFAULT  &lv_font_montserrat_20

/* ── Tema ────────────────────────────────────────────────────────────────── */
#define LV_USE_THEME_DEFAULT        1
#define LV_THEME_DEFAULT_DARK       1
#define LV_USE_THEME_SIMPLE         1

/* ── Widgets que se usan (el resto quedan por defecto) ──────────────────── */
#define LV_USE_FLEX  1
#define LV_USE_GRID  1

#endif /* LV_CONF_H */
