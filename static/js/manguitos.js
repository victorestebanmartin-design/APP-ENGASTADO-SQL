// manguitos.js — Módulo Manguitos v2

(function () {
  'use strict';

  // ── Tabla código De Manguito → alto en px (escala ~6.7px/mm) ─────────
  var ALTOS = {
    '649D10014': 32,  '649D20002': 32,  '649964A':   32,  '649964':    32,
    'H0082130':  32,  '649D10000': 32,  '649D20021': 32,
    '649D10015': 44,  '649D20000': 44,  '649962B':   44,  '649962':    44,
    'H0082132':  44,  '649D20022': 44,
    '649D10016': 64,  '649D20001': 64,  '649963B':   64,  '649963':    64,
    '649D20023': 64,
    'H0043585':  84,  '649D20003': 84,  '649965':    84,  'H0115316':  84,
    '649966': 120
  };

  // ── Tabla código De Manguito → clase CSS de color ────────────────────
  var CODIGOS = {
    '649D10014': 'amarillo', '649D10015': 'amarillo',
    '649D10016': 'amarillo', 'H0043585':  'amarillo',
    '649964A':   'amarillo', '649962B':   'amarillo',
    '649963B':   'amarillo',
    '649D20000': 'blanco',   '649D20002': 'blanco',
    '649D20001': 'blanco',   '649D20003': 'blanco',
    '649962':    'blanco',   '649963':    'blanco',
    '649964':    'blanco',   '649965':    'blanco',
    '649966':    'blanco',   '649D20021': 'blanco',
    '649D20022': 'blanco',   '649D20023': 'blanco',
    'H0082132':  'azul',     'H0082130':  'azul',
    '649D10000': 'naranja',  'H0115316':  'naranja'
  };

  var POR_PAGINA = 6;

  var elementos          = [];
  var elementosFiltrados = [];
  var codigoActivo       = null;
  var idxElem    = 0;
  var pagina     = 0;

  // ── Referencias DOM ──────────────────────────────────────────────────
  var divActivo     = document.getElementById('guiado-activo');
  var tira          = document.getElementById('tira-manguitos');
  var lblNombre     = document.getElementById('elem-nombre');
  var lblPaquete    = document.getElementById('elem-paquete-badge');
  var lblContador   = document.getElementById('elem-contador');
  var lblPagActual  = document.getElementById('pag-actual');
  var lblPagTotal   = document.getElementById('pag-total');
  var divPaginacion = document.getElementById('paginacion');
  var btnPrev           = document.getElementById('btn-elem-prev');
  var btnNext           = document.getElementById('btn-elem-next');
  var divRistraSelector = document.getElementById('ristra-selector');

  // Banner corte actual
  var corteBanner   = document.getElementById('mg-corte-banner');
  var corteCodigoEl = document.getElementById('mg-corte-codigo');
  var corteDescEl   = document.getElementById('mg-corte-desc');

  // Delegación de eventos del selector de ristra (se registra una sola vez)
  divRistraSelector.addEventListener('click', function (e) {
    var btn = e.target.closest('.ristra-btn');
    if (!btn) return;
    divRistraSelector.querySelectorAll('.ristra-btn').forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');
    aplicarFiltroRistra(btn.dataset.codigo || null);
  });

  // ── Cargar manguitos del Excel del corte ─────────────────────────────
  async function cargarGuiado(corte) {
    var archivo = corte && corte.archivo ? corte.archivo : null;
    if (!archivo) { abrirModalMg(); return; }

    try {
      var res  = await fetch('/api/manguitos/datos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archivo: archivo })
      });
      var data = await res.json();

      if (!data.success) {
        alert('Error: ' + data.error);
        abrirModalMg();
        return;
      }

      elementos = data.elementos || [];

      if (elementos.length === 0) {
        alert('No se encontraron manguitos en este corte\n(todas las filas tienen "S/M" o la columna "De Manguito" está vacía).');
        abrirModalMg();
        return;
      }

      idxElem = 0;
      pagina  = 0;
      actualizarBanner(corte);
      divActivo.style.display = 'block';
      construirBotonesRistra();
      aplicarFiltroRistra(null);

    } catch (e) {
      alert('Error de conexión: ' + e.message);
      abrirModalMg();
    }
  }

  function actualizarBanner(corte) {
    if (!corteBanner) return;
    var desc = corte.descripcion || corte.proyecto || '';
    corteCodigoEl.textContent = corte.codigo || '';
    corteDescEl.textContent = desc;
    corteBanner.classList.add('activo');
  }

  // ── Render del elemento actual ───────────────────────────────────────
  function renderElemento() {
    var elem      = elementosFiltrados[idxElem];
    var totalPags = Math.ceil(elem.manguitos.length / POR_PAGINA);
    var inicio    = pagina * POR_PAGINA;
    var slice     = elem.manguitos.slice(inicio, inicio + POR_PAGINA);

    lblNombre.textContent  = elem.elemento;
    if (lblPaquete) {
      if (elem.numero_etiqueta) {
        var codCable = (elem.manguitos[0] && elem.manguitos[0].cod_cable) || '';
        var c = (typeof getCodCableColor === 'function')
          ? getCodCableColor(codCable)
          : { bg: '#fef3c7', text: '#78350f' };
        lblPaquete.innerHTML = '<span class="elem-paquete-badge" style="background:' + c.bg +
          ';color:' + c.text + ';">🏷 #' + elem.numero_etiqueta + '</span>';
      } else {
        lblPaquete.innerHTML = '';
      }
    }
    lblContador.textContent = 'Elemento ' + (idxElem + 1) + ' de ' + elementosFiltrados.length
                            + ' · ' + elem.manguitos.length + ' manguito' + (elem.manguitos.length !== 1 ? 's' : '');

    btnPrev.disabled = (idxElem === 0 && pagina === 0);
    btnNext.disabled = (idxElem === elementosFiltrados.length - 1 && pagina >= totalPags - 1);

    // Dibujar pares en la tira
    tira.innerHTML = '';
    slice.forEach(function (m) {
      tira.appendChild(crearParManguito(m));
    });

    // Paginación
    if (totalPags > 1) {
      divPaginacion.style.display = 'flex';
      lblPagActual.textContent = pagina + 1;
      lblPagTotal.textContent  = totalPags;
    } else {
      divPaginacion.style.display = 'none';
    }
  }

  function crearParManguito(m) {
    var color = CODIGOS[m.de_manguito] || 'unknown';
    var ESCALA = 1.4;   // ampliar para mejor lectura
    var alto  = Math.round((ALTOS[m.de_manguito] || 48) * ESCALA);
    var fsIzq   = alto < 50 ? '17px' : alto < 78 ? '23px' : alto < 120 ? '28px' : '32px';
    var fsLinea = alto < 50 ? '12px' : alto < 78 ? '14px' : '16px';

    // Fila contenedora
    var row = document.createElement('div');
    row.className = 'manguito-row';
    row.style.height = alto + 'px';

    // Bloque info (cable + longitud) — fuera del manguito coloreado
    var info = document.createElement('div');
    info.className = 'manguito-info';

    if (m.cod_cable) {
      var cSpan = document.createElement('span');
      cSpan.className = 'info-cable';
      var cabTxt = m.cod_cable;
      if (m.seccion) cabTxt += ' (' + m.seccion + ')';
      cSpan.textContent = cabTxt;
      info.appendChild(cSpan);
    }
    // Etiqueta + longitud en la misma línea
    var lonEtqParts = [];
    if (m.numero_etiqueta !== null && m.numero_etiqueta !== undefined) lonEtqParts.push('#' + m.numero_etiqueta);
    if (m.longitud !== null && m.longitud !== undefined) {
      var lonVal = parseFloat(m.longitud);
      lonEtqParts.push((Math.round(lonVal * 1000) / 1000).toString().replace('.', ',') + ' m');
    }
    if (lonEtqParts.length > 0) {
      var lSpan = document.createElement('span');
      lSpan.className = 'info-lon';
      lSpan.textContent = lonEtqParts.join(' · ');
      info.appendChild(lSpan);
    }

    // Manguito coloreado (proporciones originales)
    var par = document.createElement('div');
    par.className = 'par-manguito';

    var izq = document.createElement('div');
    izq.className = 'manguito-izq mg-' + color;
    izq.style.fontSize = fsIzq;
    izq.textContent = m.de_marca || '—';

    var der = document.createElement('div');
    der.className = 'manguito-der mg-' + color;

    var l1 = document.createElement('div');
    l1.className = 'linea linea-1';
    l1.style.fontSize = fsLinea;
    l1.textContent = [m.de_elemento, m.de_punto].filter(Boolean).join('  ') || '—';

    var l2 = document.createElement('div');
    l2.className = 'linea linea-2';
    l2.style.fontSize = fsLinea;
    var txt2 = [m.para_elemento, m.para_punto].filter(Boolean).join('  ');
    l2.textContent = txt2;

    der.appendChild(l1);
    if (txt2) der.appendChild(l2);

    par.appendChild(izq);
    par.appendChild(der);

    row.appendChild(info);
    row.appendChild(par);
    return row;
  }

  // ── Selector de ristra ───────────────────────────────────────────────
  function colorToHex(c) {
    return { amarillo: '#FFE44D', blanco: '#aaa', azul: '#29B6E8', naranja: '#FF8C00' }[c] || '#ccc';
  }

  function construirBotonesRistra() {
    var totales = {};
    var orden   = [];
    elementos.forEach(function (elem) {
      elem.manguitos.forEach(function (m) {
        var c = m.de_manguito;
        if (!totales[c]) { totales[c] = 0; orden.push(c); }
        totales[c]++;
      });
    });

    divRistraSelector.innerHTML = '';
    var totalGlobal = elementos.reduce(function (a, e) { return a + e.manguitos.length; }, 0);
    var btnTodos = document.createElement('button');
    btnTodos.className = 'ristra-btn active';
    btnTodos.dataset.codigo = '';
    btnTodos.innerHTML = 'Todos <span class="ristra-count">(' + totalGlobal + ')</span>';
    divRistraSelector.appendChild(btnTodos);

    orden.forEach(function (c) {
      var btn = document.createElement('button');
      btn.className = 'ristra-btn';
      btn.dataset.codigo = c;
      btn.style.borderLeft = '5px solid ' + colorToHex(CODIGOS[c] || 'unknown');
      btn.innerHTML = c + ' <span class="ristra-count">(' + totales[c] + ')</span>';
      divRistraSelector.appendChild(btn);
    });

    divRistraSelector.style.display = 'flex';
  }

  function aplicarFiltroRistra(codigo) {
    codigoActivo = codigo;
    if (!codigo) {
      elementosFiltrados = elementos.slice();
    } else {
      elementosFiltrados = [];
      elementos.forEach(function (elem) {
        var mFilt = elem.manguitos.filter(function (m) { return m.de_manguito === codigo; });
        if (mFilt.length > 0) {
          elementosFiltrados.push({
            elemento:        elem.elemento,
            manguitos:       mFilt,
            numero_etiqueta: elem.numero_etiqueta
          });
        }
      });
      // Ordenar por numero de etiqueta
      elementosFiltrados.sort(function (a, b) {
        var fa = a.numero_etiqueta ? parseFloat(a.numero_etiqueta) : Infinity;
        var fb = b.numero_etiqueta ? parseFloat(b.numero_etiqueta) : Infinity;
        return fa - fb;
      });
    }
    idxElem = 0;
    pagina  = 0;
    renderElemento();
  }

  // ── Navegación por botones y gestos táctiles ─────────────────────
  btnNext.addEventListener('click', avanzar);
  btnPrev.addEventListener('click', retroceder);
  // Swipe izquierda → siguiente, swipe derecha → anterior
  var _swTx = 0;
  divActivo.addEventListener('touchstart', function (e) { _swTx = e.changedTouches[0].clientX; }, { passive: true });
  divActivo.addEventListener('touchend', function (e) {
    if (elementosFiltrados.length === 0) return;
    var dx = e.changedTouches[0].clientX - _swTx;
    if (Math.abs(dx) < 60) return;
    if (dx < 0) avanzar();
    else retroceder();
  }, { passive: true });

  function avanzar() {
    if (elementosFiltrados.length === 0) return;
    var totalPags = Math.ceil(elementosFiltrados[idxElem].manguitos.length / POR_PAGINA);
    if (pagina < totalPags - 1) {
      pagina++;
    } else if (idxElem < elementosFiltrados.length - 1) {
      idxElem++;
      pagina = 0;
    }
    renderElemento();
  }

  function retroceder() {
    if (elementosFiltrados.length === 0) return;
    if (pagina > 0) {
      pagina--;
    } else if (idxElem > 0) {
      idxElem--;
      pagina = Math.ceil(elementosFiltrados[idxElem].manguitos.length / POR_PAGINA) - 1;
    }
    renderElemento();
  }

  // ── Teclado ──────────────────────────────────────────────────────────
  document.addEventListener('keydown', function (e) {
    if (elementosFiltrados.length === 0) return;
    var tag = document.activeElement.tagName;
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
    if (e.key === 'Enter' || e.key === ' ')      { e.preventDefault(); avanzar(); }
    else if (e.key === 'ArrowRight')             { e.preventDefault(); avanzar(); }
    else if (e.key === 'ArrowLeft')              { e.preventDefault(); retroceder(); }
  });

  // ── Init ─────────────────────────────────────────────────────────────
  // Referencia para reabrir el modal desde el flujo de guiado
  var abrirModalMg = function () {};
  if (typeof initCableColors === 'function') initCableColors();
  initModalMg();

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ═════════════════════════════════════════════════════════════════════
  //  MODAL WIZARD MANGUITOS
  // ═════════════════════════════════════════════════════════════════════
  function initModalMg() {
    var modal       = document.getElementById('modal-mg');
    var cortes      = [];
    var flujo       = 'guiado';          // 'guiado' | 'txt_sw'
    var corteSel    = null;              // corte elegido (para txt_sw)

    var inputCorte  = document.getElementById('modal-mg-input-corte');
    var errorCorte  = document.getElementById('modal-mg-corte-error');
    var listaEl     = document.getElementById('modal-mg-lista-contenido');

    var VISTAS = ['modo', 'txttipo', 'metodo', 'input', 'lista', 'swform', 'excelform'];

    function mostrarVista(v) {
      VISTAS.forEach(function (n) {
        var el = document.getElementById('modal-mg-' + n);
        if (el) el.classList.toggle('hidden', n !== v);
      });
      if (v === 'input') {
        setTimeout(function () { if (inputCorte) inputCorte.focus(); }, 50);
      }
    }

    function abrir() { mostrarVista('modo'); modal.classList.remove('hidden'); }
    function cerrar() { modal.classList.add('hidden'); }
    abrirModalMg = abrir;   // exponer al scope exterior

    // ── Cargar lista de cortes ──────────────────────────────────────────
    async function cargarCortes() {
      try {
        var res  = await fetch('/api/codigos_cortes/listar');
        var data = await res.json();
        cortes = (data.success && data.codigos) ? data.codigos : [];
      } catch (e) {
        console.error('Error cargando cortes:', e);
        cortes = [];
      }
    }

    // ── Selección de corte (Introducir código / Lista) ──────────────────
    function irAMetodoCorte() {
      var titulo = document.getElementById('mg-metodo-titulo');
      if (titulo) titulo.textContent = (flujo === 'guiado')
        ? 'Cargar Corte para Guiado'
        : 'Cargar Corte · TXT según SW';
      mostrarVista('metodo');
    }

    function mostrarInputCorte() {
      if (errorCorte) errorCorte.classList.add('hidden');
      if (inputCorte) inputCorte.value = '';
      mostrarVista('input');
    }

    function mostrarListaCortes() {
      mostrarVista('lista');
      if (cortes.length === 0) {
        listaEl.innerHTML = '<p class="modal-bonos-vacio">No hay cortes registrados.</p>';
        return;
      }
      listaEl.innerHTML = cortes.map(function (c) {
        var desc = c.descripcion || c.proyecto || '';
        return '<div class="modal-bono-item" data-codigo="' + esc(c.codigo) + '">' +
                 '<div>' +
                   '<div class="modal-bono-item-nombre">' + esc(c.codigo) + '</div>' +
                   (desc ? '<div class="modal-bono-item-fecha">' + esc(desc) + '</div>' : '') +
                 '</div>' +
                 '<span class="modal-bono-item-arrow">▶</span>' +
               '</div>';
      }).join('');
      Array.prototype.forEach.call(listaEl.querySelectorAll('.modal-bono-item'), function (item) {
        item.addEventListener('click', function () {
          seleccionarCorte(item.getAttribute('data-codigo'));
        });
      });
    }

    function confirmarCorteCodigo() {
      var valor = inputCorte ? inputCorte.value.trim() : '';
      if (!valor) {
        if (errorCorte) { errorCorte.textContent = 'Introduce un código de corte válido.'; errorCorte.classList.remove('hidden'); }
        if (inputCorte) inputCorte.focus();
        return;
      }
      seleccionarCorte(valor);
    }

    function seleccionarCorte(codigo) {
      var cod = String(codigo || '').trim();
      var corte = cortes.find(function (c) {
        return String(c.codigo).toUpperCase() === cod.toUpperCase();
      });
      if (!corte) {
        if (errorCorte) {
          errorCorte.textContent = 'El código "' + cod + '" no está registrado.';
          errorCorte.classList.remove('hidden');
        }
        mostrarVista('input');
        if (inputCorte) { inputCorte.value = cod; inputCorte.focus(); }
        return;
      }

      if (flujo === 'guiado') {
        cerrar();
        cargarGuiado(corte);
      } else {
        // txt_sw → pasar al formulario de ref/edición
        corteSel = corte;
        var lbl = document.getElementById('mg-swform-corte');
        if (lbl) lbl.textContent = corte.codigo + (corte.descripcion ? ' · ' + corte.descripcion : '');
        mostrarVista('swform');
      }
    }

    // ── Generar TXT según SW ────────────────────────────────────────────
    async function generarTxtSw() {
      if (!corteSel) { mostrarVista('metodo'); return; }
      var btn     = document.getElementById('btn-mg-sw-generar');
      var errEl   = document.getElementById('modal-mg-sw-error');
      var ref     = (document.getElementById('mg-sw-ref').value || 'PC_CAB_BADEN').trim();
      var edicion = (document.getElementById('mg-sw-edicion').value || 'ed_04').trim();

      errEl.classList.add('hidden');
      btn.textContent = '⏳ Generando...';
      btn.disabled = true;

      try {
        var res = await fetch('/api/manguitos/generar-txt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ archivo: corteSel.archivo, ref: ref, edicion: edicion })
        });
        await descargarRespuesta(res, errEl);
      } catch (e) {
        errEl.textContent = 'Error de red: ' + e.message;
        errEl.classList.remove('hidden');
      } finally {
        btn.textContent = '⚙ Generar TXT';
        btn.disabled = false;
      }
    }

    // ── Generar TXT orden del Excel ─────────────────────────────────────
    async function generarTxtExcel() {
      var btn     = document.getElementById('btn-mg-excel-generar');
      var errEl   = document.getElementById('modal-mg-excel-error');
      var fileEl  = document.getElementById('mg-excel-file');
      var file    = fileEl ? fileEl.files[0] : null;
      if (!file) {
        errEl.textContent = 'Selecciona un archivo Excel.';
        errEl.classList.remove('hidden');
        return;
      }
      var ref     = (document.getElementById('mg-excel-ref').value || 'PC_CAB_BADEN').trim();
      var edicion = (document.getElementById('mg-excel-edicion').value || 'ed_04').trim();

      errEl.classList.add('hidden');
      btn.textContent = '⏳ Generando...';
      btn.disabled = true;

      var formData = new FormData();
      formData.append('excel', file);
      formData.append('ref', ref);
      formData.append('edicion', edicion);

      try {
        var res = await fetch('/api/manguitos/generar-txt-desde-excel', {
          method: 'POST',
          body: formData
        });
        await descargarRespuesta(res, errEl);
      } catch (e) {
        errEl.textContent = 'Error de red: ' + e.message;
        errEl.classList.remove('hidden');
      } finally {
        btn.textContent = '⚙ Generar TXT';
        btn.disabled = false;
      }
    }

    // ── Descargar respuesta (txt/zip) o mostrar error ───────────────────
    async function descargarRespuesta(res, errEl) {
      var contentType = res.headers.get('Content-Type') || '';
      if (contentType.includes('application/json')) {
        var data = await res.json();
        errEl.textContent = 'Error: ' + (data.error || 'desconocido');
        errEl.classList.remove('hidden');
        return;
      }
      var blob = await res.blob();
      var disposition = res.headers.get('Content-Disposition') || '';
      var match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
      var filename = match ? match[1].replace(/['"]/g, '') : 'manguitos.zip';
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
      alert('✅ Descarga iniciada: ' + filename);
      cerrar();
    }

    // ── Wiring de botones ───────────────────────────────────────────────
    document.getElementById('btn-mg-guiado').addEventListener('click', function () {
      flujo = 'guiado'; irAMetodoCorte();
    });
    document.getElementById('btn-mg-txt').addEventListener('click', function () {
      mostrarVista('txttipo');
    });
    document.getElementById('btn-mg-txttipo-volver').addEventListener('click', function () {
      mostrarVista('modo');
    });
    document.getElementById('btn-mg-txt-sw').addEventListener('click', function () {
      flujo = 'txt_sw'; irAMetodoCorte();
    });
    document.getElementById('btn-mg-txt-excel').addEventListener('click', function () {
      mostrarVista('excelform');
      // Abrir directamente el explorador de archivos
      var fileEl = document.getElementById('mg-excel-file');
      if (fileEl) fileEl.click();
    });

    document.getElementById('btn-mg-metodo-volver').addEventListener('click', function () {
      mostrarVista(flujo === 'guiado' ? 'modo' : 'txttipo');
    });
    document.getElementById('btn-mg-corte-input').addEventListener('click', mostrarInputCorte);
    document.getElementById('btn-mg-corte-lista').addEventListener('click', mostrarListaCortes);
    document.getElementById('btn-mg-input-volver').addEventListener('click', irAMetodoCorte);
    document.getElementById('btn-mg-input-confirmar').addEventListener('click', confirmarCorteCodigo);
    document.getElementById('btn-mg-lista-volver').addEventListener('click', irAMetodoCorte);
    if (inputCorte) {
      inputCorte.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') confirmarCorteCodigo();
      });
    }

    document.getElementById('btn-mg-sw-volver').addEventListener('click', irAMetodoCorte);
    document.getElementById('btn-mg-sw-generar').addEventListener('click', generarTxtSw);
    document.getElementById('btn-mg-excel-volver').addEventListener('click', function () {
      mostrarVista('txttipo');
    });
    document.getElementById('btn-mg-excel-generar').addEventListener('click', generarTxtExcel);

    // Botón cambiar del banner → reabrir wizard
    var btnCambiar = document.getElementById('mg-corte-cambiar');
    if (btnCambiar) btnCambiar.addEventListener('click', abrir);

    // Arranque: cargar cortes y abrir modal
    cargarCortes();
    abrir();
  }

})();
