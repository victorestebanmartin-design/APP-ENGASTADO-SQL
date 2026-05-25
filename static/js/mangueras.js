// mangueras.js — Preparación de Mangueras v1

(function () {
  'use strict';

  function badgeColor(codCable) {
    return (typeof getCodCableColor === 'function')
      ? getCodCableColor(codCable)
      : { bg: '#6b7280', text: '#fff' };
  }

  var mangueras = [];   // lista completa cargada
  var idx       = 0;   // índice actual

  // ── Referencias DOM ──────────────────────────────────────────────────
  var selArchivo  = document.getElementById('mg-archivo');
  var btnCargar   = document.getElementById('mg-cargar-btn');
  var divVacio    = document.getElementById('mg-vacio');
  var divActivo   = document.getElementById('mg-activo');
  var lblCable    = document.getElementById('mg-cable-nombre');
  var lblContador = document.getElementById('mg-contador');
  var divInfo     = document.getElementById('mg-cable-info');
  var divObsRaw   = document.getElementById('mg-obs-raw');
  var divInst     = document.getElementById('mg-instrucciones');
  var btnPrev     = document.getElementById('btn-mg-prev');
  var btnNext     = document.getElementById('btn-mg-next');

  // ── Cargar lista de archivos Excel ───────────────────────────────────
  async function cargarListaArchivos() {
    selArchivo.innerHTML = '<option value="">Selecciona un archivo Excel...</option>';
    try {
      var resp = await fetch('/api/list_files');
      var data = await resp.json();
      if (data.success && data.files) {
        data.files.forEach(function (f) {
          var opt = document.createElement('option');
          opt.value = f.nombre || f;
          opt.textContent = f.nombre || f;
          selArchivo.appendChild(opt);
        });
      }
    } catch (e) {
      console.error('Error cargando lista de archivos:', e);
    }
  }

  // ── Cargar mangueras del Excel ────────────────────────────────────────
  btnCargar.addEventListener('click', async function () {
    var archivo = selArchivo.value;
    if (!archivo) { alert('Selecciona un archivo Excel primero.'); return; }

    btnCargar.disabled = true;
    btnCargar.textContent = 'Cargando...';

    try {
      var resp = await fetch('/api/mangueras/datos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archivo: archivo })
      });
      var data = await resp.json();

      if (!data.success) {
        alert('Error: ' + (data.error || 'Error desconocido'));
        return;
      }

      mangueras = data.mangueras || [];
      if (mangueras.length === 0) {
        alert('No se encontraron filas con instrucciones de pelado (<-) en este archivo.');
        return;
      }

      idx = 0;
      divVacio.style.display  = 'none';
      divActivo.style.display = 'block';
      renderManguera();

    } catch (e) {
      alert('Error de conexión: ' + e.message);
    } finally {
      btnCargar.disabled = false;
      btnCargar.textContent = 'Cargar';
    }
  });

  // ── Renderizar manguera actual ────────────────────────────────────────
  function renderManguera() {
    var mg = mangueras[idx];
    if (!mg) return;

    // Cabecera — cable + badge etiqueta
    var badgeHtml = '';
    if (mg.numero_etiqueta) {
      var c = badgeColor(mg.cod_cable);
      badgeHtml = ' <span id="mg-etq-badge" style="' +
        'background:' + c.bg + ';color:' + c.text + ';' +
        'font-size:14px;font-weight:800;padding:3px 10px;border-radius:12px;' +
        'vertical-align:middle;margin-left:8px;">' +
        '🏷 #' + mg.numero_etiqueta + '</span>';
    }
    lblCable.innerHTML = esc(mg.cable_marca || '—') + badgeHtml;
    lblContador.textContent = (idx + 1) + ' / ' + mangueras.length;

    // Info cable
    divInfo.innerHTML = infoHtml(mg);

    // Obs raw
    divObsRaw.textContent = mg.observaciones_raw || '';

    // Instrucciones
    divInst.innerHTML = instruccionesHtml(mg);

    // Botones nav
    btnPrev.disabled = (idx === 0);
    btnNext.disabled = (idx === mangueras.length - 1);
  }

  function infoHtml(mg) {
    var html = '';
    // Badge de etiqueta destacado en la info si existe
    if (mg.numero_etiqueta) {
      var c = badgeColor(mg.cod_cable);
      html += '<div class="info-item">' +
                '<span class="info-label">Paquete / Etiqueta</span>' +
                '<span style="display:inline-flex;align-items:center;gap:6px;">' +
                  '<span style="background:' + c.bg + ';color:' + c.text + ';' +
                    'font-size:18px;font-weight:900;padding:4px 14px;border-radius:14px;">' +
                    '#' + mg.numero_etiqueta +
                  '</span>' +
                '</span>' +
              '</div>';
    }
    if (mg.de_elemento) {
      html += itemInfo('Elemento', mg.de_elemento);
    }
    if (mg.de_terminal && mg.de_terminal !== 'S/T') {
      html += itemInfo('De Terminal', mg.de_terminal);
    }
    if (mg.de_terminal || mg.para_terminal) {
      html += '<div class="info-arrow">→</div>';
    }
    if (mg.para_terminal && mg.para_terminal !== 'S/T') {
      html += itemInfo('Para Terminal', mg.para_terminal);
    }
    return html;
  }

  function itemInfo(label, val) {
    return '<div class="info-item">' +
             '<span class="info-label">' + esc(label) + '</span>' +
             '<span class="info-val">' + esc(val) + '</span>' +
           '</div>';
  }

  function instruccionesHtml(mg) {
    var html = '';
    html += ladoHtml(mg.de,   '← Lado De',   'lado-de');
    html += ladoHtml(mg.para, 'Lado Para →', 'lado-para');
    return html;
  }

  function ladoHtml(inst, titulo, clase) {
    if (!inst) {
      return '<div class="lado-card lado-vacio">' +
               '<div class="lado-title">⬜ ' + titulo + '</div>' +
               '<div style="color:#d1d5db; font-size:14px;">Sin instrucciones</div>' +
             '</div>';
    }

    var rows = '';
    var pmVal = inst.pm;  // puede ser null si no se especificó

    // PM (pelado manguera)
    rows += instFila('Pelado Manguera',
      pmVal !== null && pmVal !== undefined
        ? '<span class="inst-val val-pm">' + pmVal + '</span><span class="inst-unit">mm</span>'
        : '<span class="val-dash">—</span>');

    // Malla: si no se especifica, queda a la misma longitud que el pelado de manguera
    if (inst.m_cortar) {
      rows += instFila('Malla',
        '<span class="inst-val val-cortar">✂ CORTAR</span>');
    } else if (inst.m_mrs) {
      rows += instFila('Malla',
        '<span class="inst-val" style="color:#b45309;">↩ Hacia atrás</span>' +
        '<span style="font-size:10px;color:#9ca3af;margin-left:6px;">sin retráctil</span>');
    } else if (inst.m_mrc) {
      var mrcMedida = inst.m_mrc_medida;
      rows += instFila('Malla',
        '<span class="inst-val" style="color:#b45309;">↩ Hacia atrás</span>' +
        '<span style="font-size:10px;color:#9ca3af;margin-left:6px;">con retráctil</span>' +
        (mrcMedida !== null && mrcMedida !== undefined
          ? '<br><span style="font-size:11px;color:#6d28d9;">Retráctil: <strong>' + mrcMedida + ' mm</strong></span>'
          : ''));
    } else if (inst.m !== null && inst.m !== undefined) {
      rows += instFila('Pelado Malla',
        '<span class="inst-val val-malla">' + inst.m + '</span><span class="inst-unit">mm</span>');
    } else {
      // Sin instrucción de malla → igual que el pelado de manguera
      rows += instFila('Pelado Malla',
        pmVal !== null && pmVal !== undefined
          ? '<span class="inst-val val-malla" title="Igual que pelado de manguera">' + pmVal + '</span>' +
            '<span class="inst-unit">mm</span>' +
            '<span style="font-size:10px;color:#9ca3af;margin-left:4px;">(= manguera)</span>'
          : '<span class="val-dash">—</span>');
    }

    // Activos: si no se especifica, quedan a la medida del pelado de manguera
    if (inst.a_todos !== null && inst.a_todos !== undefined) {
      rows += instFila('Activos (todos)',
        '<span class="inst-val val-activo">' + inst.a_todos + '</span><span class="inst-unit">mm</span>');
    } else if (inst.a_especificos && Object.keys(inst.a_especificos).length > 0) {
      var keys = Object.keys(inst.a_especificos).sort(function (a, b) { return +a - +b; });
      keys.forEach(function (k) {
        rows += instFila('Activo ' + k,
          '<span class="inst-val val-activo">' + inst.a_especificos[k] + '</span><span class="inst-unit">mm</span>');
      });
    } else {
      // Sin instrucción de activos → quedan a la medida del pelado de manguera
      rows += instFila('Activos',
        pmVal !== null && pmVal !== undefined
          ? '<span class="inst-val val-activo" title="Igual que pelado de manguera">' + pmVal + '</span>' +
            '<span class="inst-unit">mm</span>' +
            '<span style="font-size:10px;color:#9ca3af;margin-left:4px;">(= manguera)</span>'
          : '<span class="val-dash">—</span>');
    }

    return '<div class="lado-card ' + clase + '">' +
             '<div class="lado-title">' + titulo + '</div>' +
             rows +
           '</div>';
  }

  function instFila(label, valHtml) {
    return '<div class="inst-row">' +
             '<span class="inst-label">' + esc(label) + '</span>' +
             '<span>' + valHtml + '</span>' +
           '</div>';
  }

  // ── Navegación y gestos táctiles ─────────────────────────────────────
  btnPrev.addEventListener('click', function () { if (idx > 0) { idx--; renderManguera(); } });
  btnNext.addEventListener('click', function () { if (idx < mangueras.length - 1) { idx++; renderManguera(); } });
  // Swipe izquierda → siguiente, swipe derecha → anterior
  var _swTx = 0;
  divActivo.addEventListener('touchstart', function (e) { _swTx = e.changedTouches[0].clientX; }, { passive: true });
  divActivo.addEventListener('touchend', function (e) {
    if (mangueras.length === 0) return;
    var dx = e.changedTouches[0].clientX - _swTx;
    if (Math.abs(dx) < 60) return;
    if (dx < 0 && idx < mangueras.length - 1) { idx++; renderManguera(); }
    else if (dx > 0 && idx > 0) { idx--; renderManguera(); }
  }, { passive: true });

  document.addEventListener('keydown', function (e) {
    if (mangueras.length === 0) return;
    if (['INPUT', 'SELECT', 'TEXTAREA'].indexOf(e.target.tagName) !== -1) return;
    if (e.key === 'ArrowLeft'  && idx > 0)                        { idx--; renderManguera(); }
    if (e.key === 'ArrowRight' && idx < mangueras.length - 1)     { idx++; renderManguera(); }
    if ((e.key === 'Enter' || e.key === ' ') && idx < mangueras.length - 1) {
      e.preventDefault();
      idx++;
      renderManguera();
    }
  });

  // ── Utilidades ────────────────────────────────────────────────────────
  function esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // ── Init ─────────────────────────────────────────────────────────────
  if (typeof initCableColors === 'function') initCableColors();
  cargarListaArchivos();

})();
