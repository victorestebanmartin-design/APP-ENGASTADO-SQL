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

  var POR_PAGINA = 8;

  var elementos          = [];
  var elementosFiltrados = [];
  var codigoActivo       = null;
  var idxElem    = 0;
  var pagina     = 0;

  // ── Referencias DOM ──────────────────────────────────────────────────
  var selArchivo    = document.getElementById('guiado-archivo');
  var btnCargar     = document.getElementById('guiado-cargar-btn');
  var divVacio      = document.getElementById('guiado-vacio');
  var divActivo     = document.getElementById('guiado-activo');
  var tira          = document.getElementById('tira-manguitos');
  var lblNombre     = document.getElementById('elem-nombre');
  var lblContador   = document.getElementById('elem-contador');
  var lblPagActual  = document.getElementById('pag-actual');
  var lblPagTotal   = document.getElementById('pag-total');
  var divPaginacion = document.getElementById('paginacion');
  var btnPrev           = document.getElementById('btn-elem-prev');
  var btnNext           = document.getElementById('btn-elem-next');
  var divRistraSelector = document.getElementById('ristra-selector');

  // Delegación de eventos del selector de ristra (se registra una sola vez)
  divRistraSelector.addEventListener('click', function (e) {
    var btn = e.target.closest('.ristra-btn');
    if (!btn) return;
    divRistraSelector.querySelectorAll('.ristra-btn').forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');
    aplicarFiltroRistra(btn.dataset.codigo || null);
  });

  // ── Tabs ─────────────────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
      document.querySelectorAll('.tab-panel').forEach(function (p) { p.classList.remove('active'); });
      btn.classList.add('active');
      var panel = document.getElementById('tab-' + btn.dataset.tab);
      if (panel) panel.classList.add('active');
    });
  });

  // ── Cargar lista de archivos Excel ───────────────────────────────────
  async function cargarListaArchivos() {
    // Limpiar opciones previas (evita duplicados si se llama más de una vez)
    selArchivo.innerHTML = '<option value="">Selecciona un archivo Excel...</option>';
    try {
      var res  = await fetch('/api/list_files');
      var data = await res.json();
      if (data.success && data.files) {
        data.files.forEach(function (f) {
          var nombre = (typeof f === 'object') ? f.nombre : f;
          var opt = document.createElement('option');
          opt.value = nombre;
          opt.textContent = nombre;
          selArchivo.appendChild(opt);
        });
      }
    } catch (e) {
      console.error('Error cargando lista de archivos:', e);
    }
  }

  // ── Cargar manguitos del Excel seleccionado ──────────────────────────
  btnCargar.addEventListener('click', async function () {
    var archivo = selArchivo.value;
    if (!archivo) { alert('Selecciona un archivo Excel'); return; }

    btnCargar.textContent = 'Cargando...';
    btnCargar.disabled = true;

    try {
      var res  = await fetch('/api/manguitos/datos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archivo: archivo })
      });
      var data = await res.json();

      if (!data.success) {
        alert('Error: ' + data.error);
        return;
      }

      elementos = data.elementos || [];

      if (elementos.length === 0) {
        alert('No se encontraron manguitos en este archivo\n(todas las filas tienen "S/M" o la columna "De Manguito" está vacía).');
        return;
      }

      idxElem = 0;
      pagina  = 0;
      divVacio.style.display  = 'none';
      divActivo.style.display = 'block';
      construirBotonesRistra();
      aplicarFiltroRistra(null);

    } catch (e) {
      alert('Error de conexión: ' + e.message);
    } finally {
      btnCargar.textContent = 'Cargar';
      btnCargar.disabled = false;
    }
  });

  // ── Render del elemento actual ───────────────────────────────────────
  function renderElemento() {
    var elem      = elementosFiltrados[idxElem];
    var totalPags = Math.ceil(elem.manguitos.length / POR_PAGINA);
    var inicio    = pagina * POR_PAGINA;
    var slice     = elem.manguitos.slice(inicio, inicio + POR_PAGINA);

    var numEtiqueta = elem.numero_etiqueta ? ' [#' + elem.numero_etiqueta + ']' : '';
    lblNombre.textContent  = elem.elemento + numEtiqueta;
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
    var alto  = ALTOS[m.de_manguito] || 48;
    var fsIzq   = alto < 38 ? '13px' : alto < 56 ? '17px' : alto < 90 ? '21px' : '24px';
    var fsLinea = alto < 38 ?  '9px' : alto < 56 ? '11px' : '12px';

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

  // ── Navegación por botones ───────────────────────────────────────────
  btnNext.addEventListener('click', avanzar);
  btnPrev.addEventListener('click', retroceder);

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
  cargarListaArchivos();

  // ── Generar TXT de pedido (Fase 3) ───────────────────────────────────
  (function () {
    var selPedidoArchivo = document.getElementById('pedido-archivo');
    var inputRef         = document.getElementById('pedido-ref');
    var inputEdicion     = document.getElementById('pedido-edicion');
    var btnGenerar       = document.getElementById('pedido-generar-btn');
    var divResultado     = document.getElementById('pedido-resultado');
    var tablaBody        = document.getElementById('pedido-tabla-body');
    var divError         = document.getElementById('pedido-error');

    if (!selPedidoArchivo) return;

    // Cargar lista de archivos en el select de pedido (reutiliza el mismo endpoint)
    async function cargarListaArchivosPedido() {
      selPedidoArchivo.innerHTML = '<option value="">Selecciona un archivo Excel...</option>';
      try {
        var res  = await fetch('/api/list_files');
        var data = await res.json();
        if (data.success && data.files) {
          data.files.forEach(function (f) {
            var nombre = (typeof f === 'object') ? f.nombre : f;
            var opt = document.createElement('option');
            opt.value = nombre;
            opt.textContent = nombre;
            selPedidoArchivo.appendChild(opt);
          });
        }
      } catch (e) {
        console.error('Error cargando lista de archivos pedido:', e);
      }
    }

    btnGenerar.addEventListener('click', async function () {
      var archivo = selPedidoArchivo.value;
      if (!archivo) { alert('Selecciona un archivo Excel'); return; }
      var ref     = (inputRef.value || 'PC_CAB_BADEN').trim();
      var edicion = (inputEdicion.value || 'ed_04').trim();

      btnGenerar.textContent = '⏳ Generando...';
      btnGenerar.disabled = true;
      divResultado.style.display = 'none';
      divError.style.display = 'none';

      try {
        var res = await fetch('/api/manguitos/generar-txt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ archivo: archivo, ref: ref, edicion: edicion })
        });

        // Si el servidor devuelve JSON es un error
        var contentType = res.headers.get('Content-Type') || '';
        if (contentType.includes('application/json')) {
          var data = await res.json();
          divError.textContent = 'Error: ' + (data.error || 'desconocido');
          divError.style.display = 'block';
          return;
        }

        // Descargar el fichero (txt o zip)
        var blob = await res.blob();
        var disposition = res.headers.get('Content-Disposition') || '';
        var match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
        var filename = match ? match[1].replace(/['"]/g, '') : 'manguitos.zip';
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = filename; a.click();
        URL.revokeObjectURL(url);

        divResultado.innerHTML = '<p style="color:#16a34a;font-weight:600;">Descarga iniciada: ' + filename + '</p>';
        divResultado.style.display = 'block';

      } catch (e) {
        divError.textContent = 'Error de red: ' + e.message;
        divError.style.display = 'block';
      } finally {
        btnGenerar.textContent = '⚙ Generar TXT';
        btnGenerar.disabled = false;
      }
    });

    cargarListaArchivosPedido();
  })();

  // ── Generar TXT desde Excel propio (Tab excel) ────────────────────────
  (function () {
    var inputFile   = document.getElementById('excel-file-input');
    var inputRef    = document.getElementById('excel-ref');
    var inputEdicion = document.getElementById('excel-edicion');
    var btnGenerar  = document.getElementById('excel-generar-btn');
    var divResultado = document.getElementById('excel-resultado');
    var tablaBody   = document.getElementById('excel-tabla-body');
    var divError    = document.getElementById('excel-error');

    if (!btnGenerar) return;

    btnGenerar.addEventListener('click', async function () {
      var file = inputFile ? inputFile.files[0] : null;
      if (!file) { alert('Selecciona un archivo Excel'); return; }

      var ref     = (inputRef ? inputRef.value : 'PC_CAB_BADEN').trim() || 'PC_CAB_BADEN';
      var edicion = (inputEdicion ? inputEdicion.value : 'ed_04').trim() || 'ed_04';

      btnGenerar.textContent = 'Generando...';
      btnGenerar.disabled = true;
      divResultado.style.display = 'none';
      divError.style.display = 'none';

      var formData = new FormData();
      formData.append('excel', file);
      formData.append('ref', ref);
      formData.append('edicion', edicion);

      try {
        var res  = await fetch('/api/manguitos/generar-txt-desde-excel', {
          method: 'POST',
          body: formData   // sin Content-Type para que el browser ponga el boundary
        });

        // Si el servidor devuelve JSON es un error
        var contentType = res.headers.get('Content-Type') || '';
        if (contentType.includes('application/json')) {
          var data = await res.json();
          divError.textContent = 'Error: ' + (data.error || 'desconocido');
          divError.style.display = 'block';
          return;
        }

        // Descargar el fichero (txt o zip)
        var blob = await res.blob();
        var disposition = res.headers.get('Content-Disposition') || '';
        var match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
        var filename = match ? match[1].replace(/['"]/g, '') : 'manguitos.zip';
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = filename; a.click();
        URL.revokeObjectURL(url);

        divResultado.innerHTML = '<p style="color:#16a34a;font-weight:600;">Descarga iniciada: ' + filename + '</p>';
        divResultado.style.display = 'block';

      } catch (e) {
        divError.textContent = 'Error de red: ' + e.message;
        divError.style.display = 'block';
      } finally {
        btnGenerar.textContent = 'Generar TXT';
        btnGenerar.disabled = false;
      }
    });
  })();

})();
