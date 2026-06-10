/**
 * cable-colors.js — Color fijo por Cod. cable (sin colisiones)
 * Los colores se cargan desde la BD (/api/cable-colores) mediante initCableColors().
 * El mapa estático MAPA sirve de fallback si la BD no responde.
 * GRUPO_SERIE (etiquetas padre de serie) → dorado #f59e0b.
 * Cables desconocidos → hash fallback.
 */
(function (global) {
  'use strict';

  // Mapa estático base (se sobreescribe con datos de BD al llamar initCableColors)
  var MAPA = {
    '640361':      '#0f766e',  // teal oscuro
    '640362':      '#b45309',  // ambar oscuro
    '640C10006A':  '#4d7c0f',  // lima oscuro
    '640C10008A':  '#7c3aed',  // violeta
    '640C10014':   '#be185d',  // fucsia
    '640C10021A':  '#4f46e5',  // indigo
    '640C10022A':  '#0891b2',  // cyan
    '640C10023':   '#dc2626',  // rojo
    '640C10024A':  '#65a30d',  // lima
    '640C10025A':  '#059669',  // verde esmeralda
    '640C10040A':  '#0e7490',  // cyan oscuro
    '640C10041':   '#db2777',  // rosa
    '640D10002':   '#2563eb',  // azul
    '640D10009A':  '#1d4ed8',  // azul oscuro
    '640D10017':   '#d97706',  // ambar
    '640D10023':   '#b91c1c',  // rojo oscuro
    '640D10029A':  '#047857',  // verde oscuro
    '640D20000':   '#6d28d9',  // morado
    'GRUPO_SERIE': '#f59e0b',  // dorado — etiquetas padre de serie
    'H0211195':    '#831843',  // rosa oscuro
  };

  // Paleta de fallback para cables no listados
  var PALETA = [
    '#d97706','#2563eb','#059669','#7c3aed','#dc2626','#0891b2',
    '#db2777','#65a30d','#0d9488','#ea580c','#4f46e5','#be185d',
  ];

  // Color de texto explícito por cable (desde BD). null/ausente = auto por luminancia.
  var MAPA_TEXTO = {};

  // Luminancia WCAG: devuelve '#000000' o '#ffffff' según el fondo hex.
  function _autoTextColor(hex) {
    try {
      var h = String(hex || '').replace('#', '');
      if (h.length !== 6) return '#ffffff';
      var r = parseInt(h.slice(0, 2), 16),
          g = parseInt(h.slice(2, 4), 16),
          b = parseInt(h.slice(4, 6), 16);
      function lin(c) { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
      var L = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
      return L > 0.179 ? '#000000' : '#ffffff';
    } catch (e) { return '#ffffff'; }
  }

  function _textoPara(key, bg) {
    var txt = MAPA_TEXTO[key];
    if (txt && /^#[0-9a-fA-F]{6}$/.test(txt)) return txt;
    return _autoTextColor(bg);
  }

  function getCodCableColor(codCable) {
    if (!codCable || String(codCable).trim() === '' || String(codCable).toLowerCase() === 'nan') {
      return { bg: '#6b7280', text: '#fff' };
    }
    var key = String(codCable).trim().toUpperCase();
    if (MAPA[key]) {
      return { bg: MAPA[key], text: _textoPara(key, MAPA[key]) };
    }
    // Hash fallback para cables no listados
    var h = 0;
    for (var i = 0; i < key.length; i++) {
      h = (h * 31 + key.charCodeAt(i)) >>> 0;
    }
    var bg = PALETA[h % PALETA.length];
    return { bg: bg, text: _textoPara(key, bg) };
  }

  /**
   * Carga los colores desde la BD y actualiza MAPA en memoria.
   * Llamar una vez al inicio de cada vista (es async, no bloquea el render inicial).
   */
  async function initCableColors() {
    try {
      var resp = await fetch('/api/cable-colores');
      if (!resp.ok) return;
      var data = await resp.json();
      if (data.success && Array.isArray(data.colores)) {
        data.colores.forEach(function (c) {
          var key = c.cod_cable.toUpperCase();
          MAPA[key] = c.color_hex;
          MAPA_TEXTO[key] = c.color_texto || null;
        });
      }
    } catch (e) {
      // Silencioso — el mapa estático sigue funcionando
    }
  }

  global.getCodCableColor = getCodCableColor;
  global.initCableColors  = initCableColors;

})(window);

