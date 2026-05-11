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

  function getCodCableColor(codCable) {
    if (!codCable || String(codCable).trim() === '' || String(codCable).toLowerCase() === 'nan') {
      return { bg: '#6b7280', text: '#fff' };
    }
    var key = String(codCable).trim().toUpperCase();
    if (MAPA[key]) {
      return { bg: MAPA[key], text: '#fff' };
    }
    // Hash fallback para cables no listados
    var h = 0;
    for (var i = 0; i < key.length; i++) {
      h = (h * 31 + key.charCodeAt(i)) >>> 0;
    }
    return { bg: PALETA[h % PALETA.length], text: '#fff' };
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
          MAPA[c.cod_cable.toUpperCase()] = c.color_hex;
        });
      }
    } catch (e) {
      // Silencioso — el mapa estático sigue funcionando
    }
  }

  global.getCodCableColor = getCodCableColor;
  global.initCableColors  = initCableColors;

})(window);

