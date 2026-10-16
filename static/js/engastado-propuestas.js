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

  var lista = document.getElementById('ep-lista');
  if (!lista) return;
  var estado = document.getElementById('ep-status');
  var propuestas = [];
  var puedeAprobar = false;
  var identidadId = null;
  var RESULTADOS = {
    aplicado: 'aplicado', ya_bloqueado: 'ya tenía *', heredado: 'heredado de la ED anterior',
    no_encontrado: 'no encontrado en el Excel', ambiguo: 'varias filas iguales, no aplicado',
    revertido: 'revertido', no_aplicable: 'el * no era de esta propuesta'
  };
  function textoResultado(resultado) {
    if (!resultado) return '';
    if (resultado.indexOf('no_heredado_') === 0) return 'no heredado: ' + (RESULTADOS[resultado.slice(12)] || resultado.slice(12));
    return RESULTADOS[resultado] || resultado;
  }
  function render() {
    var filtro = document.getElementById('ep-filtro').value;
    lista.innerHTML = propuestas.filter(function (propuesta) { return !filtro || propuesta.estado === filtro; }).map(function (propuesta) {
      var cables = propuesta.cables.map(function (cable) {
        return '<li>' + esc(cable.cable_marca) + ' · ' + esc(cable.cod_cable) + ' · ' + esc(cable.elemento) +
          (cable.serie ? ' · ' + esc(cable.serie) : '') + ' · lado ' + (cable.lado === 'de' ? 'De (liso)' : 'Para (guion)') +
          ' · ' + esc(cable.archivo) + (cable.fila ? ' fila ' + cable.fila : '') +
          (cable.resultado ? ' — <em>' + esc(textoResultado(cable.resultado)) + '</em>' : '') + '</li>';
      }).join('');
      var propia = propuesta.autor_id === identidadId;
      var acciones = '';
      if (propuesta.estado === 'pendiente') {
        var puedeResolver = puedeAprobar && !propia;
        acciones = '<div class="mp-actions">' +
          '<button type="button" class="mp-aprobar" data-id="' + propuesta.id + '" data-accion="aprobar"' + (puedeResolver ? '' : ' disabled') + '>Aprobar</button>' +
          '<button type="button" class="mp-rechazar" data-id="' + propuesta.id + '" data-accion="rechazar"' + (puedeResolver ? '' : ' disabled') + '>Rechazar</button></div>' +
          (!puedeAprobar ? '<p class="mp-resolution-warning">Sesion personal de Administracion requerida.</p>' :
            propia ? '<p class="mp-resolution-warning">Esta propuesta debe resolverla otro administrador.</p>' : '');
      } else if (propuesta.estado === 'aprobada') {
        acciones = '<div class="mp-actions"><button type="button" data-id="' + propuesta.id + '" data-accion="revertir"' +
          (puedeAprobar ? '' : ' disabled') + '>Revertir (volver a pedir el terminal)</button></div>';
      }
      return '<article class="mp-propuesta"><h2>#' + propuesta.id + ' · Terminal ' + esc(propuesta.terminal) + ' · ' + esc(propuesta.paquete) + ' · ' + esc(propuesta.estado) + '</h2>' +
        '<p>' + esc(propuesta.autor_nombre + ' · ' + propuesta.creada_at + ' · ' + propuesta.archivo) + '</p>' +
        '<p>Motivo: ' + esc(propuesta.motivo) + '</p><ul>' + cables + '</ul>' +
        (propuesta.resuelta_at ? '<p>' + esc(propuesta.responsable_nombre + ' · ' + propuesta.resuelta_at + '\n' + propuesta.motivo_resolucion) + '</p>' : '') +
        (propuesta.revertida_at ? '<p>Revertida: ' + esc(propuesta.revertida_por + ' · ' + propuesta.revertida_at + '\n' + propuesta.motivo_reversion) + '</p>' : '') +
        acciones + '</article>';
    }).join('') || '<p>No hay propuestas en este estado.</p>';
  }
  async function cargar() {
    try {
      var respuesta = await fetch('/api/engastado/propuestas');
      var datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error);
      propuestas = datos.propuestas;
      puedeAprobar = datos.aprobar;
      identidadId = datos.operario_id;
      document.getElementById('ep-identidad-actual').textContent = datos.nombre + (datos.aprobar ? ' / Administración' : datos.recuperacion ? '' : ' / Operario');
      document.getElementById('ep-contador').textContent = datos.pendientes + (datos.pendientes === 1 ? ' pendiente' : ' pendientes');
      estado.textContent = '';
      render();
    } catch (error) { estado.textContent = error.message; }
  }
  document.getElementById('ep-actualizar').addEventListener('click', cargar);
  document.getElementById('ep-filtro').addEventListener('change', render);
  var dialogo = document.getElementById('ep-resolucion');
  var formulario = document.getElementById('ep-resolucion-form');
  var TITULOS = { aprobar: 'Aprobar', rechazar: 'Rechazar', revertir: 'Revertir' };
  lista.addEventListener('click', function (evento) {
    var boton = evento.target.closest('[data-accion]');
    if (!boton) return;
    formulario.dataset.id = boton.dataset.id;
    formulario.dataset.accion = boton.dataset.accion;
    document.getElementById('ep-resolucion-titulo').textContent = TITULOS[boton.dataset.accion] + ' propuesta #' + boton.dataset.id;
    document.getElementById('ep-resolucion-motivo').value = '';
    document.getElementById('ep-resolucion-error').textContent = '';
    dialogo.showModal();
  });
  document.getElementById('ep-resolucion-cancelar').addEventListener('click', function () { dialogo.close(); });
  formulario.addEventListener('submit', async function (evento) {
    evento.preventDefault();
    var boton = formulario.querySelector('[type=submit]');
    var accion = formulario.dataset.accion;
    boton.disabled = true;
    try {
      var url = '/api/engastado/propuestas/' + formulario.dataset.id + (accion === 'revertir' ? '/revertir' : '/resolver');
      var respuesta = await fetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accion: accion, motivo: document.getElementById('ep-resolucion-motivo').value })
      });
      var datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error);
      dialogo.close();
      document.getElementById('ep-filtro').value = { aprobar: 'aprobada', rechazar: 'rechazada', revertir: 'revertida' }[accion];
      await cargar();
      estado.textContent = {
        aprobar: 'Propuesta aprobada. El terminal ya no se pide en esos cables.',
        rechazar: 'Propuesta rechazada. El Excel no cambia.',
        revertir: 'Propuesta revertida. El terminal se vuelve a pedir en esos cables.'
      }[accion];
      await actualizarContadores();
      try { localStorage.setItem('engastado-propuestas-resueltas', String(Date.now())); } catch (error) { return; }
    } catch (error) { document.getElementById('ep-resolucion-error').textContent = error.message; }
    finally { boton.disabled = false; }
  });
  cargar();
})();
