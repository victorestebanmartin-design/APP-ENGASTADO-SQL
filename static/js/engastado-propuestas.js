(function () {
  'use strict';
  function esc(valor) {
    return String(valor == null ? '' : valor).replace(/[&<>"']/g, function (caracter) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[caracter];
    });
  }

  // Contador del menú de Admin (data-engastado-pendientes), como el de mangueras.
  async function actualizarContadores() {
    if (!document.querySelector('[data-engastado-pendientes]')) return;
    try {
      var respuesta = await fetch('/api/engastado/propuestas/pendientes');
      var datos = await respuesta.json();
      if (datos.success) document.querySelectorAll('[data-engastado-pendientes]').forEach(function (elemento) {
        elemento.textContent = 'Propuestas de engastado (' + datos.pendientes + (datos.pendientes === 1 ? ' pendiente)' : ' pendientes)');
      });
    } catch (error) { return; }
  }
  actualizarContadores();
  setInterval(function () { if (document.visibilityState === 'visible') actualizarContadores(); }, 60000);
  window.addEventListener('storage', function (evento) {
    if (evento.key === 'engastado-propuestas-resueltas') actualizarContadores();
  });

  // ── Pantalla de Propuestas de engastado ────────────────────────────────
  var lista = document.getElementById('ep-lista');
  if (!lista) return;

  var propuestas = [];
  var puedeAprobar = false;
  var identidadId = null;
  var filtro = 'pendiente';
  var seleccion = new Set();
  var ultimaMarcada = null;   // para seleccionar un rango con Mayús
  var ocupado = false;

  var RESULTADOS = {
    aplicado: 'aplicado', ya_bloqueado: 'ya tenía *', heredado: 'heredado de la ED anterior',
    no_encontrado: 'no encontrado en el Excel', ambiguo: 'varias filas iguales, no aplicado',
    revertido: 'revertido', no_aplicable: 'el * no era de esta propuesta'
  };
  var VERBOS = {
    aprobar: { gerundio: 'Aprobando', hecho: 'aprobada', hechos: 'aprobadas' },
    rechazar: { gerundio: 'Rechazando', hecho: 'rechazada', hechos: 'rechazadas' },
    revertir: { gerundio: 'Revirtiendo', hecho: 'revertida', hechos: 'revertidas' }
  };

  function textoResultado(resultado) {
    if (!resultado) return '';
    if (resultado.indexOf('no_heredado_') === 0) return 'no heredado: ' + (RESULTADOS[resultado.slice(12)] || resultado.slice(12));
    return RESULTADOS[resultado] || resultado;
  }
  function fecha(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso || '');
    return m ? m[3] + '/' + m[2] + '/' + m[1].slice(2) + ' ' + m[4] + ':' + m[5] : (iso || '');
  }
  function propia(p) { return identidadId != null && p.autor_id === identidadId; }
  // Qué se puede hacer con una propuesta desde esta sesión
  function acciones(p) {
    if (!puedeAprobar) return [];
    if (p.estado === 'pendiente') return propia(p) ? [] : ['aprobar', 'rechazar'];
    if (p.estado === 'aprobada') return ['revertir'];
    return [];
  }
  function numerosPaquete(p) {
    return p.cables.map(function (c) { return c.paquete; })
      .filter(function (n, i, todos) { return n && todos.indexOf(n) === i; });
  }
  function textoBusqueda(p) {
    return [p.id, p.terminal, p.paquete, p.archivo, p.autor_nombre, p.motivo, p.responsable_nombre,
      numerosPaquete(p).join(' ')].concat(p.cables.map(function (c) {
      return [c.cable_marca, c.cod_cable, c.elemento, c.serie].join(' ');
    })).join(' ').toLowerCase();
  }
  function visibles() {
    var buscar = document.getElementById('ep-buscar').value.trim().toLowerCase();
    var palabras = buscar ? buscar.split(/\s+/) : [];
    return propuestas.filter(function (p) {
      if (filtro && p.estado !== filtro) return false;
      if (!palabras.length) return true;
      var texto = textoBusqueda(p);
      return palabras.every(function (palabra) { return texto.indexOf(palabra) !== -1; });
    });
  }

  function filaHtml(p) {
    var posibles = acciones(p);
    var marcable = posibles.length > 0;
    var numeros = numerosPaquete(p);
    var cables = p.cables.map(function (c) {
      return '<li>' + (c.paquete ? '<span class="extra">Paq ' + esc(c.paquete) + ' · </span>' : '') +
        '<span class="marca">' + esc(c.cable_marca) + '</span>' +
        ' <span class="extra">· ' + esc(c.elemento) + (c.serie ? ' · ' + esc(c.serie) : '') +
        ' · ' + (c.lado === 'de' ? 'De (liso)' : 'Para (guion)') +
        (c.archivo !== p.archivo ? ' · ' + esc(c.archivo) : '') + (c.fila ? ' · fila ' + c.fila : '') + '</span>' +
        (c.resultado ? ' <span class="res">— ' + esc(textoResultado(c.resultado)) + '</span>' : '') + '</li>';
    }).join('');
    var corte = (p.motivo || '').indexOf(': ');
    var motivo = corte > 0
      ? '<span class="cat">' + esc(p.motivo.slice(0, corte)) + '</span><span class="det">' + esc(p.motivo.slice(corte + 2)) + '</span>'
      : '<span class="cat">' + esc(p.motivo) + '</span>';
    var decision = '';
    if (p.resuelta_at) decision += '<div class="ep-decision">' + esc((p.estado === 'rechazada' ? 'Rechazó ' : 'Aprobó ') +
      p.responsable_nombre + ' · ' + fecha(p.resuelta_at) + (p.motivo_resolucion ? ' — ' + p.motivo_resolucion : '')) + '</div>';
    if (p.revertida_at) decision += '<div class="ep-decision">' + esc('Revirtió ' + p.revertida_por + ' · ' +
      fecha(p.revertida_at) + (p.motivo_reversion ? ' — ' + p.motivo_reversion : '')) + '</div>';
    var botones = posibles.map(function (accion) {
      return {
        aprobar: '<button type="button" class="ep-btn ok" data-accion="aprobar" title="Aprobar: el terminal deja de pedirse">&#10003; Aprobar</button>',
        rechazar: '<button type="button" class="ep-btn ko" data-accion="rechazar" title="Rechazar: el Excel no cambia">&#10007; Rechazar</button>',
        revertir: '<button type="button" class="ep-btn rev" data-accion="revertir" title="Volver a pedir el terminal">&#8634; Revertir</button>'
      }[accion];
    }).join('');
    if (p.estado === 'pendiente' && puedeAprobar && propia(p)) botones = '<span class="ep-propia">Tuya: la resuelve otro admin</span>';
    var marcada = seleccion.has(p.id);
    return '<tr data-id="' + p.id + '"' + (marcada ? ' class="sel"' : '') + '>' +
      '<td class="ep-check"><input type="checkbox" data-marcar' + (marcada ? ' checked' : '') + (marcable ? '' : ' disabled') + ' aria-label="Seleccionar propuesta ' + p.id + '"></td>' +
      '<td class="ep-id"><span>#' + p.id + '</span>' + (filtro ? '' : '<br><span class="ep-estado ' + esc(p.estado) + '">' + esc(p.estado) + '</span>') + '</td>' +
      '<td class="ep-term">' + esc(p.terminal) +
        '<small>' + (numeros.length ? 'Paquete ' + esc(numeros.join(', ')) + ' · ' : '') + esc(p.paquete) + '</small>' +
        '<small>' + esc(p.archivo) + '</small></td>' +
      '<td><ul class="ep-cables">' + cables + '</ul></td>' +
      '<td class="ep-motivo">' + motivo + decision + '</td>' +
      '<td class="ep-quien">' + esc(p.autor_nombre) + '<small>' + esc(fecha(p.creada_at)) + '</small></td>' +
      '<td class="ep-acciones">' + botones + '</td></tr>';
  }

  function render() {
    var filas = visibles();
    // La selección solo vale para lo que se ve
    var ids = new Set(filas.map(function (p) { return p.id; }));
    seleccion.forEach(function (id) { if (!ids.has(id)) seleccion.delete(id); });
    lista.innerHTML = filas.map(filaHtml).join('') ||
      '<tr><td colspan="7" class="ep-vacio">' + (filtro === 'pendiente' ? 'No hay propuestas pendientes.' : 'No hay propuestas en este estado.') + '</td></tr>';
    pintarSeleccion();
  }

  function pintarSeleccion() {
    var filas = visibles();
    var marcables = filas.filter(function (p) { return acciones(p).length; });
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
    var cuenta = function (accion) { return elegidas.filter(function (p) { return acciones(p).indexOf(accion) !== -1; }).length; };
    var barra = document.getElementById('ep-barra');
    barra.classList.toggle('visible', seleccion.size > 0);
    document.getElementById('ep-cuantas').textContent = seleccion.size + (seleccion.size === 1 ? ' seleccionada' : ' seleccionadas');
    barra.querySelectorAll('[data-masivo]').forEach(function (boton) {
      var n = cuenta(boton.dataset.masivo);
      boton.hidden = n === 0;
      boton.disabled = ocupado;
    });
  }

  function contar() {
    ['pendiente', 'aprobada', 'rechazada', 'revertida'].forEach(function (est) {
      var n = propuestas.filter(function (p) { return p.estado === est; }).length;
      document.getElementById('ep-n-' + est).textContent = n ? '(' + n + ')' : '';
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
      var respuesta = await fetch('/api/engastado/propuestas');
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
        var url = '/api/engastado/propuestas/' + ids[i] + (accion === 'revertir' ? '/revertir' : '/resolver');
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
      try { localStorage.setItem('engastado-propuestas-resueltas', String(Date.now())); } catch (error) { /* sin almacenamiento */ }
    }
    await cargar();
    var texto = hechas ? hechas + ' ' + (hechas === 1 ? verbo.hecho : verbo.hechos) + '.' : '';
    if (hechas && accion === 'aprobar') texto += ' El terminal ya no se pide en esos cables.';
    if (hechas && accion === 'revertir') texto += ' El terminal se vuelve a pedir.';
    if (errores.length) aviso((texto ? texto + '\n' : '') + 'No se ' + (errores.length === 1 ? 'pudo' : 'pudieron') + ':\n' + errores.join('\n'), 'error');
    else aviso(texto, 'success');
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
      if (accion === 'revertir' && !window.confirm('¿Revertir la propuesta #' + id + '? El terminal se vuelve a pedir en esos cables.')) return;
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
    if (accion === 'revertir' && !window.confirm('¿Revertir ' + ids.length + (ids.length === 1 ? ' propuesta' : ' propuestas') + '? El terminal se vuelve a pedir.')) return;
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
})();
