// Lista de propuestas con el tema de Admin, compartida por Propuestas de
// engastado y Propuestas de mangueras: pestañas por estado, buscador,
// selección múltiple y aprobar / rechazar / deshacer de un clic (el
// comentario es opcional). Cada pantalla pone sus columnas con `celdas`.
//
// Espera en la página los ids ep-lista, ep-tabs, ep-n-<estado>, ep-buscar,
// ep-actualizar, ep-status, ep-todas, ep-barra, ep-cuantas, ep-comentario,
// ep-deseleccionar, ep-toast, ep-identidad-actual y ep-aviso-admin.
window.listaPropuestas = function (config) {
  'use strict';
  var lista = document.getElementById('ep-lista');
  if (!lista) return;

  var propuestas = [];
  var puedeAprobar = false;
  var identidadId = null;
  var filtro = 'pendiente';
  var seleccion = new Set();
  var ultimaMarcada = null;   // para seleccionar un rango con Mayús
  var ocupado = false;
  var deshacer = config.deshacer;   // { accion: 'revertir', ... }

  var VERBOS = {
    aprobar: { gerundio: 'Aprobando', hecho: 'aprobada', hechos: 'aprobadas' },
    rechazar: { gerundio: 'Rechazando', hecho: 'rechazada', hechos: 'rechazadas' }
  };
  VERBOS[deshacer.accion] = deshacer.verbos;
  // Mangueras dice "Aceptar" donde engastado dice "Aprobar"
  var botonAprobar = (config.aprobar && config.aprobar.boton) || 'Aprobar';
  if (config.aprobar && config.aprobar.verbos) VERBOS.aprobar = config.aprobar.verbos;

  function esc(valor) {
    return String(valor == null ? '' : valor).replace(/[&<>"']/g, function (caracter) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[caracter];
    });
  }
  function fecha(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || '');
    return m ? m[3] + '/' + m[2] + '/' + m[1].slice(2) + ' ' + m[4] + ':' + m[5] : (iso || '');
  }
  // Motivo "Categoria: detalle" en dos líneas
  function motivoHtml(motivo) {
    var corte = (motivo || '').indexOf(': ');
    return corte > 0
      ? '<span class="cat">' + esc(motivo.slice(0, corte)) + '</span><span class="det">' + esc(motivo.slice(corte + 2)) + '</span>'
      : '<span class="cat">' + esc(motivo) + '</span>';
  }
  var ayudas = { esc: esc, fecha: fecha, motivoHtml: motivoHtml };

  function propia(p) { return identidadId != null && p.autor_id === identidadId; }
  // Qué se puede hacer con una propuesta desde esta sesión
  function acciones(p) {
    if (!puedeAprobar) return [];
    if (p.estado === 'pendiente') return propia(p) ? [] : ['aprobar', 'rechazar'];
    if (p.estado === 'aprobada') return [deshacer.accion];
    return [];
  }
  function visibles() {
    var buscar = document.getElementById('ep-buscar').value.trim().toLowerCase();
    var palabras = buscar ? buscar.split(/\s+/) : [];
    return propuestas.filter(function (p) {
      if (filtro && p.estado !== filtro) return false;
      if (!palabras.length) return true;
      var texto = [p.id, p.archivo, p.autor_nombre, p.motivo, p.responsable_nombre, config.buscar(p)].join(' ').toLowerCase();
      return palabras.every(function (palabra) { return texto.indexOf(palabra) !== -1; });
    });
  }

  function decisionHtml(p) {
    var html = '';
    if (p.resuelta_at) html += '<div class="ep-decision">' + esc((p.estado === 'rechazada' ? 'Rechazó ' : (config.aprobar && config.aprobar.hecho) || 'Aprobó ') +
      p.responsable_nombre + ' · ' + fecha(p.resuelta_at) + (p.motivo_resolucion ? ' — ' + p.motivo_resolucion : '')) + '</div>';
    var deshecha = deshacer.campos;
    if (p[deshecha.at]) html += '<div class="ep-decision">' + esc(deshacer.etiqueta + ' ' + p[deshecha.por] + ' · ' +
      fecha(p[deshecha.at]) + (p[deshecha.motivo] ? ' — ' + p[deshecha.motivo] : '')) + '</div>';
    return html;
  }

  function filaHtml(p) {
    var posibles = acciones(p);
    var botones = posibles.map(function (accion) {
      if (accion === 'aprobar') return '<button type="button" class="ep-btn ok" data-accion="aprobar" title="' + esc(config.ayudaAprobar) + '">&#10003; ' + esc(botonAprobar) + '</button>';
      if (accion === 'rechazar') return '<button type="button" class="ep-btn ko" data-accion="rechazar" title="' + esc(config.ayudaRechazar) + '">&#10007; Rechazar</button>';
      return '<button type="button" class="ep-btn rev" data-accion="' + deshacer.accion + '" title="' + esc(deshacer.ayuda) + '">&#8634; ' + esc(deshacer.boton) + '</button>';
    }).join('');
    if (p.estado === 'pendiente' && puedeAprobar && propia(p)) botones = '<span class="ep-propia">Tuya: la resuelve otro admin</span>';
    var marcada = seleccion.has(p.id);
    return '<tr data-id="' + p.id + '"' + (marcada ? ' class="sel"' : '') + '>' +
      '<td class="ep-check"><input type="checkbox" data-marcar' + (marcada ? ' checked' : '') + (posibles.length ? '' : ' disabled') + ' aria-label="Seleccionar propuesta ' + p.id + '"></td>' +
      '<td class="ep-id"><span>#' + p.id + '</span>' + (filtro ? '' : '<br><span class="ep-estado ' + esc(p.estado) + '">' + esc(p.estado) + '</span>') + '</td>' +
      config.celdas(p, ayudas) +
      '<td class="ep-motivo">' + motivoHtml(p.motivo) + decisionHtml(p) + '</td>' +
      '<td class="ep-quien">' + esc(p.autor_nombre) + '<small>' + esc(fecha(p.creada_at)) + '</small></td>' +
      '<td class="ep-acciones"><div class="ep-botones">' + botones + '</div></td></tr>';
  }

  function render() {
    var filas = visibles();
    // La selección solo vale para lo que se ve
    var ids = new Set(filas.map(function (p) { return p.id; }));
    seleccion.forEach(function (id) { if (!ids.has(id)) seleccion.delete(id); });
    lista.innerHTML = filas.map(filaHtml).join('') ||
      '<tr><td colspan="' + config.columnas + '" class="ep-vacio">' + (filtro === 'pendiente' ? 'No hay propuestas pendientes.' : 'No hay propuestas en este estado.') + '</td></tr>';
    pintarSeleccion();
  }

  function pintarSeleccion() {
    var marcables = visibles().filter(function (p) { return acciones(p).length; });
    var todas = document.getElementById('ep-todas');
    todas.disabled = !marcables.length;
    todas.checked = marcables.length > 0 && marcables.every(function (p) { return seleccion.has(p.id); });
    todas.indeterminate = !todas.checked && seleccion.size > 0;
    lista.querySelectorAll('tr[data-id]').forEach(function (tr) {
      var marcada = seleccion.has(Number(tr.dataset.id));
      tr.classList.toggle('sel', marcada);
      var check = tr.querySelector('[data-marcar]');
      if (check) check.checked = marcada;
    });
    var elegidas = propuestas.filter(function (p) { return seleccion.has(p.id); });
    var barra = document.getElementById('ep-barra');
    barra.classList.toggle('visible', seleccion.size > 0);
    document.getElementById('ep-cuantas').textContent = seleccion.size + (seleccion.size === 1 ? ' seleccionada' : ' seleccionadas');
    barra.querySelectorAll('[data-masivo]').forEach(function (boton) {
      boton.hidden = !elegidas.some(function (p) { return acciones(p).indexOf(boton.dataset.masivo) !== -1; });
      boton.disabled = ocupado;
    });
  }

  function contar() {
    config.estados.forEach(function (est) {
      var n = propuestas.filter(function (p) { return p.estado === est; }).length;
      var contador = document.getElementById('ep-n-' + est);
      if (contador) contador.textContent = n ? '(' + n + ')' : '';
    });
  }

  var temporizadorToast = null;
  function aviso(texto, tipo) {
    var toast = document.getElementById('ep-toast');
    toast.textContent = texto;
    toast.className = 'mensaje ep-toast visible ' + (tipo || 'success');
    clearTimeout(temporizadorToast);
    temporizadorToast = setTimeout(function () { toast.classList.remove('visible'); }, tipo === 'error' ? 9000 : 4000);
  }

  async function cargar() {
    var estado = document.getElementById('ep-status');
    try {
      var respuesta = await fetch(config.api);
      var datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error || 'No se pudieron cargar las propuestas.');
      propuestas = datos.propuestas;
      puedeAprobar = datos.aprobar;
      identidadId = datos.operario_id;
      document.getElementById('ep-identidad-actual').textContent = datos.nombre + (datos.aprobar ? ' · Administración' : datos.recuperacion ? '' : ' · Operario');
      document.getElementById('ep-aviso-admin').hidden = !!datos.aprobar;
      estado.classList.add('hidden');
      contar();
      render();
    } catch (error) {
      estado.textContent = error.message;
      estado.classList.remove('hidden');
    }
  }

  // Resuelve una o varias, de una en una: cada una es su propia escritura del
  // Excel, y si alguna falla las demás siguen.
  async function ejecutar(ids, accion, comentario) {
    if (ocupado || !ids.length) return;
    ocupado = true;
    pintarSeleccion();
    var verbo = VERBOS[accion];
    var hechas = 0;
    var errores = [];
    for (var i = 0; i < ids.length; i++) {
      if (ids.length > 1) aviso(verbo.gerundio + ' ' + (i + 1) + ' de ' + ids.length + '…', 'success');
      try {
        var url = config.api + '/' + ids[i] + (accion === deshacer.accion ? '/' + deshacer.accion : '/resolver');
        var respuesta = await fetch(url, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ accion: accion, motivo: comentario || '' })
        });
        var datos = await respuesta.json().catch(function () { return {}; });
        if (!respuesta.ok) throw new Error(datos.error || ('Error ' + respuesta.status));
        hechas++;
        seleccion.delete(ids[i]);
      } catch (error) {
        errores.push('#' + ids[i] + ': ' + error.message);
      }
    }
    ocupado = false;
    if (hechas) {
      document.getElementById('ep-comentario').value = '';
      try { localStorage.setItem(config.claveAviso, String(Date.now())); } catch (error) { /* sin almacenamiento */ }
      if (config.alResolver) config.alResolver();
    }
    await cargar();
    var texto = hechas ? hechas + ' ' + (hechas === 1 ? verbo.hecho : verbo.hechos) + '.' : '';
    if (hechas && config.mensajes[accion]) texto += ' ' + config.mensajes[accion];
    if (errores.length) aviso((texto ? texto + '\n' : '') + 'No se ' + (errores.length === 1 ? 'pudo' : 'pudieron') + ':\n' + errores.join('\n'), 'error');
    else aviso(texto, 'success');
  }

  function confirmarDeshacer(cuantas) {
    return window.confirm('¿' + deshacer.boton + ' ' + (cuantas === 1 ? 'esta propuesta' : cuantas + ' propuestas') + '? ' + deshacer.ayuda + '.');
  }

  // ── Eventos ────────────────────────────────────────────────────────────
  document.getElementById('ep-tabs').addEventListener('click', function (evento) {
    var tab = evento.target.closest('.ep-tab');
    if (!tab) return;
    filtro = tab.dataset.estado;
    document.querySelectorAll('.ep-tab').forEach(function (t) { t.classList.toggle('activa', t === tab); });
    seleccion.clear();
    ultimaMarcada = null;
    render();
  });
  document.getElementById('ep-buscar').addEventListener('input', render);
  document.getElementById('ep-actualizar').addEventListener('click', cargar);

  document.getElementById('ep-todas').addEventListener('change', function (evento) {
    visibles().forEach(function (p) {
      if (!acciones(p).length) return;
      if (evento.target.checked) seleccion.add(p.id); else seleccion.delete(p.id);
    });
    pintarSeleccion();
  });

  function marcar(id, valor, conRango) {
    var filas = visibles().filter(function (p) { return acciones(p).length; });
    var idx = filas.findIndex(function (p) { return p.id === id; });
    if (idx === -1) return;
    var desde = idx;
    if (conRango && ultimaMarcada != null) {
      var previo = filas.findIndex(function (p) { return p.id === ultimaMarcada; });
      if (previo !== -1) desde = previo;
    }
    filas.slice(Math.min(desde, idx), Math.max(desde, idx) + 1).forEach(function (p) {
      if (valor) seleccion.add(p.id); else seleccion.delete(p.id);
    });
    ultimaMarcada = id;
    pintarSeleccion();
  }

  lista.addEventListener('click', function (evento) {
    var tr = evento.target.closest('tr[data-id]');
    if (!tr) return;
    var id = Number(tr.dataset.id);
    var boton = evento.target.closest('[data-accion]');
    if (boton) {
      var accion = boton.dataset.accion;
      if (accion === deshacer.accion && !confirmarDeshacer(1)) return;
      ejecutar([id], accion, '');
      return;
    }
    if (evento.target.closest('a, button')) return;
    var check = tr.querySelector('[data-marcar]');
    if (!check || check.disabled) return;
    // Clic en la casilla o en cualquier sitio de la fila: alterna la selección
    var valor = evento.target === check ? check.checked : !seleccion.has(id);
    marcar(id, valor, evento.shiftKey);
  });
  // Evita que Mayús+clic seleccione texto de la tabla
  lista.addEventListener('mousedown', function (evento) { if (evento.shiftKey) evento.preventDefault(); });

  document.getElementById('ep-barra').addEventListener('click', function (evento) {
    var boton = evento.target.closest('[data-masivo]');
    if (!boton) return;
    var accion = boton.dataset.masivo;
    var ids = propuestas.filter(function (p) { return seleccion.has(p.id) && acciones(p).indexOf(accion) !== -1; })
      .map(function (p) { return p.id; });
    if (accion === deshacer.accion && !confirmarDeshacer(ids.length)) return;
    ejecutar(ids, accion, document.getElementById('ep-comentario').value.trim());
  });
  document.getElementById('ep-deseleccionar').addEventListener('click', function () {
    seleccion.clear();
    ultimaMarcada = null;
    pintarSeleccion();
  });
  document.addEventListener('keydown', function (evento) {
    if (evento.key === 'Escape' && seleccion.size && !ocupado) { seleccion.clear(); pintarSeleccion(); }
  });

  cargar();
};
