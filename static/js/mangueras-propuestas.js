(function () {
  'use strict';
  function esc(valor) {
    return String(valor == null ? '' : valor).replace(/[&<>"']/g, function (caracter) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[caracter];
    });
  }
  var ultimoPendientes = null;
  async function actualizarContadores(forzar) {
    if (!document.querySelector('[data-mangueras-pendientes]')) return;
    try {
      var respuesta = await fetch('/api/mangueras/propuestas/pendientes');
      var datos = await respuesta.json();
      if (datos.success) document.querySelectorAll('[data-mangueras-pendientes]').forEach(function (elemento) {
        elemento.textContent = 'Propuestas de mangueras (' + datos.pendientes + (datos.pendientes === 1 ? ' pendiente)' : ' pendientes)');
      });
      if (datos.success && (forzar || ultimoPendientes !== datos.pendientes)) {
        ultimoPendientes = datos.pendientes;
        document.dispatchEvent(new CustomEvent('mangueras-pendientes-actualizadas'));
      }
    } catch (error) { return; }
  }
  actualizarContadores();
  setInterval(function () { if (document.visibilityState === 'visible') actualizarContadores(); }, 60000);
  window.addEventListener('storage', function (evento) {
    if (evento.key === 'mangueras-propuestas-resueltas') actualizarContadores(true);
  });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') actualizarContadores(true);
  });
  window.identificarMangueras = async function () {
    var respuesta = await fetch('/api/mangueras/identificacion');
    var datos = await respuesta.json();
    if (!respuesta.ok) throw new Error(datos.error || 'Entra al modulo con tu sesion de operario.');
    return datos;
  };

  function medidas(inst, retractiles) {
    inst = inst || {};
    var malla = inst.m == null ? inst.pm : inst.m;
    var unidadMalla = 'mm';
    if (inst.m_cortar) { malla = 'Cortar'; unidadMalla = ''; }
    else if (inst.m_mrs || inst.m_mrc) {
      var longitud = inst.m_mrc ? inst.m_mrc_medida : inst.m_mrs_medida;
      malla = (longitud == null ? 'Sin medida' : longitud + ' mm') + ' hacia atr\u00e1s ' + (inst.m_mrc ? 'con' : 'sin') + ' retr\u00e1ctil';
      unidadMalla = '';
    }
    var resultado = [
      { clave: 'pm', etiqueta: 'Pelado manguera', valor: inst.pm, unidad: 'mm', clase: 'val-pm' },
      { clave: 'malla', etiqueta: 'Malla', valor: malla, unidad: unidadMalla, clase: 'val-malla' },
      { clave: 'activos', etiqueta: 'Activos', valor: inst.a_todos == null ? inst.pm : inst.a_todos, unidad: 'mm', clase: 'val-activo' }
    ];
    Object.keys(inst.a_especificos || {}).sort(function (primero, segundo) { return Number(primero) - Number(segundo); }).forEach(function (activo) {
      resultado.push({ clave: 'activo:' + activo, etiqueta: 'Activo ' + activo, valor: inst.a_especificos[activo], unidad: 'mm', clase: 'val-activo' });
    });
    (retractiles || []).forEach(function (retractil, posicion) {
      resultado.push({ clave: 'retractil:' + posicion, etiqueta: 'Retr\u00e1ctil', valor: retractil.codigo + ' / ' + retractil.medida + ' mm', unidad: '', clase: 'val-retractil' });
    });
    if ((inst.otros_tokens || []).length) resultado.push({ clave: 'otros', etiqueta: 'Otras instrucciones', valor: inst.otros_tokens.join(' / '), unidad: '', clase: '' });
    return resultado;
  }
  window.medidasMangueraHtml = function (original, sugerido, lado, soloCambios) {
    var antes = medidas(original[lado], original['retractil_' + lado]);
    var despues = medidas(sugerido[lado], sugerido['retractil_' + lado]);
    var claves = Array.from(new Set(antes.concat(despues).map(function (campo) { return campo.clave; })));
    return claves.map(function (clave) {
      var actual = antes.find(function (campo) { return campo.clave === clave; });
      var propuesto = despues.find(function (campo) { return campo.clave === clave; });
      if (!actual && clave.indexOf('activo:') === 0) actual = Object.assign({}, propuesto, { valor: antes.find(function (campo) { return campo.clave === 'activos'; }).valor });
      if (!propuesto && clave.indexOf('activo:') === 0) propuesto = Object.assign({}, actual, { valor: despues.find(function (campo) { return campo.clave === 'activos'; }).valor });
      var cambio = !actual || !propuesto || actual.valor !== propuesto.valor || actual.unidad !== propuesto.unidad;
      if (soloCambios && !cambio) return '';
      var campo = actual || propuesto;
      var vigente = actual && actual.valor != null ? actual.valor : 'Sin medida';
      var sugerencia = propuesto && propuesto.valor != null ? propuesto.valor : 'Sin medida';
      var unidadesIguales = actual && propuesto && actual.unidad === propuesto.unidad;
      return '<div class="inst-row mp-line"><span class="inst-label">' + esc(campo.etiqueta) + '</span><span>' +
        '<span class="inst-val ' + esc(campo.clase) + '">' + esc(vigente) + '</span>' +
        (cambio ? '<span class="mp-sugerido"> (' + esc(sugerencia) + (!unidadesIguales && propuesto ? ' ' + esc(propuesto.unidad) : '') + ')</span>' : '') +
        '<span class="inst-unit">' + esc(actual ? actual.unidad : '') + '</span></span></div>';
    }).join('');
  };
  window.comparacionMangueras = function (original, sugerido) {
    var lados = ['de', 'para'].map(function (lado) {
      var cambios = window.medidasMangueraHtml(original, sugerido, lado, true);
      return cambios ? '<section class="mp-side"><h3>' + (lado === 'de' ? 'Lado De (liso)' : 'Lado Para (guion)') + '</h3>' + cambios + '</section>' : '';
    }).join('');
    var notas = ['observaciones_mangueras', 'aviso_mangueras'].map(function (campo) {
      if ((original[campo] || '') === (sugerido[campo] || '')) return '';
      return '<p class="mp-notas"><strong>' + (campo === 'aviso_mangueras' ? 'Aviso' : 'Observaciones') + ':</strong> ' +
        esc(original[campo] || 'Sin texto') + '<span class="mp-sugerido"> (' + esc(sugerido[campo] || 'Sin texto') + ')</span></p>';
    }).join('');
    return '<div class="mp-medidas">' + lados + '</div>' + notas;
  };

  var lista = document.getElementById('mp-lista');
  if (!lista) return;
  var estado = document.getElementById('mp-status');
  var propuestas = [];
  var puedeAprobar = false;
  var identidadId = null;
  function render() {
    var filtro = document.getElementById('mp-filtro').value;
    lista.innerHTML = propuestas.filter(function (propuesta) { return !filtro || propuesta.estado === filtro; }).map(function (propuesta) {
      var filas = propuesta.sugerido.filas;
      var comparaciones = propuesta.sugerido.cambios.map(function (cambio) {
        var original = propuesta.original.find(function (fila) { return fila.fila === cambio.fila; });
        var sugerido = filas.find(function (fila) { return fila.fila === cambio.fila; });
        return '<h3>' + esc(original.cable_marca + ' / ' + original.cod_cable + ' / ' + original.de_elemento + ' / Fila ' + original.fila) + '</h3>' + window.comparacionMangueras(original, sugerido);
      }).join('');
      var puedeResolver = puedeAprobar && propuesta.autor_id !== identidadId;
      var avisoResolucion = !puedeAprobar ? 'Sesion personal de Administracion requerida.' :
        propuesta.autor_id === identidadId ? 'Esta propuesta debe resolverla otro administrador.' : '';
      var acciones = propuesta.estado === 'pendiente' ? '<div class="mp-actions">' +
        '<button type="button" class="mp-aprobar" data-resolver="' + propuesta.id + '" data-accion="aprobar"' + (puedeResolver ? '' : ' disabled') + '>Aprobar</button>' +
        '<button type="button" class="mp-rechazar" data-resolver="' + propuesta.id + '" data-accion="rechazar"' + (puedeResolver ? '' : ' disabled') + '>Rechazar</button></div>' +
        (avisoResolucion ? '<p class="mp-resolution-warning">' + esc(avisoResolucion) + '</p>' : '') : '';
      return '<article class="mp-propuesta"><h2>#' + propuesta.id + ' · ' + esc(propuesta.archivo) + ' · ' + esc(propuesta.estado) + '</h2>' +
        '<p>' + esc(propuesta.autor_nombre + ' · ' + propuesta.creada_at) + '</p><p>Motivo: ' + esc(propuesta.motivo) + '</p>' + comparaciones +
        (propuesta.resuelta_at ? '<p>' + esc(propuesta.responsable_nombre + ' · ' + propuesta.resuelta_at + '\n' + propuesta.motivo_resolucion) + '</p>' : '') +
        acciones + '</article>';
    }).join('') || '<p>No hay propuestas en este estado.</p>';
  }
  async function cargar() {
    try {
      var respuesta = await fetch('/api/mangueras/propuestas');
      var datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error);
      propuestas = datos.propuestas;
      puedeAprobar = datos.aprobar;
      identidadId = datos.operario_id;
      document.getElementById('mp-identidad-actual').textContent = datos.nombre + (datos.aprobar ? ' / Administraci\u00f3n' : datos.recuperacion ? '' : ' / Operario');
      document.getElementById('mp-contador').textContent = datos.pendientes + (datos.pendientes === 1 ? ' pendiente' : ' pendientes');
      estado.textContent = '';
      render();
    } catch (error) { estado.textContent = error.message; }
  }
  document.getElementById('mp-actualizar').addEventListener('click', cargar);
  document.getElementById('mp-filtro').addEventListener('change', render);
  var resolucion = document.getElementById('mp-resolucion');
  lista.addEventListener('click', function (evento) {
    var boton = evento.target.closest('[data-resolver]');
    if (!boton) return;
    document.getElementById('mp-resolucion-form').dataset.id = boton.dataset.resolver;
    document.getElementById('mp-resolucion-form').dataset.accion = boton.dataset.accion;
    document.getElementById('mp-resolucion-titulo').textContent = (boton.dataset.accion === 'aprobar' ? 'Aprobar' : 'Rechazar') + ' propuesta #' + boton.dataset.resolver;
    document.getElementById('mp-resolucion-motivo').value = '';
    document.getElementById('mp-resolucion-error').textContent = '';
    resolucion.showModal();
  });
  document.getElementById('mp-resolucion-cancelar').addEventListener('click', function () { resolucion.close(); });
  document.getElementById('mp-resolucion-form').addEventListener('submit', async function (evento) {
    evento.preventDefault();
    var boton = evento.target.querySelector('[type=submit]');
    boton.disabled = true;
    try {
      var respuesta = await fetch('/api/mangueras/propuestas/' + evento.target.dataset.id + '/resolver', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
          accion: evento.target.dataset.accion, motivo: document.getElementById('mp-resolucion-motivo').value
        })
      });
      var datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error);
      var aprobada = evento.target.dataset.accion === 'aprobar';
      resolucion.close();
      document.getElementById('mp-filtro').value = aprobada ? 'aprobada' : 'rechazada';
      await cargar();
      estado.textContent = aprobada ? 'Propuesta aceptada. La nueva preparacion ya esta aplicada al corte.' :
        'Propuesta rechazada. Se conserva la preparacion vigente sin los cambios sugeridos.';
      await actualizarContadores();
      try { localStorage.setItem('mangueras-propuestas-resueltas', String(Date.now())); } catch (error) { return; }
    } catch (error) { document.getElementById('mp-resolucion-error').textContent = error.message; }
    finally { boton.disabled = false; }
  });
  cargar();
})();