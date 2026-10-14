(function () {
  'use strict';
  function esc(valor) {
    return String(valor == null ? '' : valor).replace(/[&<>"']/g, function (caracter) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[caracter];
    });
  }
  var dialogo = document.getElementById('mp-identidad');
  var ultimoPendientes = null;
  async function actualizarContadores() {
    if (!document.querySelector('[data-mangueras-pendientes]')) return;
    try {
      var respuesta = await fetch('/api/mangueras/propuestas/pendientes');
      var datos = await respuesta.json();
      if (datos.success) document.querySelectorAll('[data-mangueras-pendientes]').forEach(function (elemento) {
        elemento.textContent = 'Propuestas de mangueras (' + datos.pendientes + (datos.pendientes === 1 ? ' pendiente)' : ' pendientes)');
      });
      if (datos.success && ultimoPendientes !== datos.pendientes) {
        ultimoPendientes = datos.pendientes;
        document.dispatchEvent(new CustomEvent('mangueras-pendientes-actualizadas'));
      }
    } catch (error) { return; }
  }
  actualizarContadores();
  setInterval(function () { if (document.visibilityState === 'visible') actualizarContadores(); }, 60000);
  if (!dialogo) return;
  var promesaIdentidad = null;
  var resolverIdentidad = null;
  window.identificarMangueras = function () {
    if (promesaIdentidad) return promesaIdentidad;
    promesaIdentidad = new Promise(function (resolve) { resolverIdentidad = resolve; });
    document.getElementById('mp-identidad-error').textContent = '';
    document.getElementById('mp-clave').value = '';
    dialogo.showModal();
    fetch('/api/operarios').then(function (respuesta) { return respuesta.json(); }).then(function (datos) {
      document.getElementById('mp-operario').innerHTML = '<option value="">Seleccionar operario</option>' +
        (datos.operarios || []).filter(function (operario) { return operario.activo && operario.clave_personal_configurada; }).map(function (operario) {
          return '<option value="' + esc(operario.id) + '">' + esc(operario.nombre) + '</option>';
        }).join('');
      if (!document.getElementById('mp-operario').options[1]) {
        document.getElementById('mp-identidad-error').textContent = 'No hay claves personales configuradas en Admin > Operarios.';
      }
    }).catch(function () { document.getElementById('mp-identidad-error').textContent = 'No se pudo cargar la lista de operarios.'; });
    return promesaIdentidad;
  };
  dialogo.addEventListener('close', function () {
    document.getElementById('mp-clave').value = '';
    if (resolverIdentidad) resolverIdentidad(null);
    resolverIdentidad = null;
    promesaIdentidad = null;
  });
  document.getElementById('mp-identidad-cancelar').addEventListener('click', function () { dialogo.close(); });
  document.getElementById('mp-identidad-form').addEventListener('submit', async function (evento) {
    evento.preventDefault();
    var boton = evento.target.querySelector('[type=submit]');
    boton.disabled = true;
    try {
      var respuesta = await fetch('/api/mangueras/identificacion', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operario_id: document.getElementById('mp-operario').value, clave: document.getElementById('mp-clave').value })
      });
      document.getElementById('mp-clave').value = '';
      var datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error || 'No se pudo identificar.');
      resolverIdentidad(datos);
      resolverIdentidad = null;
      dialogo.close();
    } catch (error) { document.getElementById('mp-identidad-error').textContent = error.message; }
    finally { boton.disabled = false; }
  });

  function instrucciones(inst) {
    if (!inst) return 'Sin instrucciones';
    var partes = [];
    if (inst.pm != null) partes.push('Pelado manguera: ' + inst.pm + ' mm');
    if (inst.m_cortar) partes.push('Malla: cortar');
    else if (inst.m_mrs || inst.m_mrc) partes.push('Malla hacia atr\u00e1s ' + (inst.m_mrc ? 'con' : 'sin') + ' retr\u00e1ctil: ' +
      ((inst.m_mrc ? inst.m_mrc_medida : inst.m_mrs_medida) == null ? 'sin medida' : (inst.m_mrc ? inst.m_mrc_medida : inst.m_mrs_medida) + ' mm'));
    else partes.push('Pelado malla: ' + (inst.m == null ? 'igual que manguera' : inst.m + ' mm'));
    if (inst.a_todos != null || !Object.keys(inst.a_especificos || {}).length) {
      partes.push('Activos: ' + (inst.a_todos == null ? 'igual que manguera' : inst.a_todos + ' mm'));
    }
    Object.keys(inst.a_especificos || {}).forEach(function (activo) { partes.push('Activo ' + activo + ': ' + inst.a_especificos[activo] + ' mm'); });
    return partes.concat(inst.otros_tokens || []).join('\n');
  }
  function retractiles(lista) { return (lista || []).map(function (item) { return item.codigo + ': ' + item.medida + ' mm'; }).join('\n') || 'Sin retr\u00e1ctiles'; }
  window.comparacionMangueras = function (original, sugerido) {
    var campos = [
      ['Lado De (liso)', instrucciones(original.de), instrucciones(sugerido.de)],
      ['Lado Para (guion)', instrucciones(original.para), instrucciones(sugerido.para)],
      ['Retr\u00e1ctiles De', retractiles(original.retractil_de), retractiles(sugerido.retractil_de)],
      ['Retr\u00e1ctiles Para', retractiles(original.retractil_para), retractiles(sugerido.retractil_para)],
      ['Observaciones', original.observaciones_mangueras || '', sugerido.observaciones_mangueras || ''],
      ['Aviso', original.aviso_mangueras || '', sugerido.aviso_mangueras || '']
    ];
    return '<div class="mp-comparacion"><table><thead><tr><th>Preparaci\u00f3n</th><th>Original</th><th>Sugerido</th></tr></thead><tbody>' + campos.map(function (campo) {
      return '<tr><th scope="row">' + esc(campo[0]) + '</th><td>' + esc(campo[1]) + '</td><td>' + esc(campo[2]) + '</td></tr>';
    }).join('') + '</tbody></table></div>';
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
      return '<article class="mp-propuesta"><h2>#' + propuesta.id + ' · ' + esc(propuesta.archivo) + ' · ' + esc(propuesta.estado) + '</h2>' +
        '<p>' + esc(propuesta.autor_nombre + ' · ' + propuesta.creada_at) + '</p><p>Motivo: ' + esc(propuesta.motivo) + '</p>' + comparaciones +
        (propuesta.resuelta_at ? '<p>' + esc(propuesta.responsable_nombre + ' · ' + propuesta.resuelta_at + '\n' + propuesta.motivo_resolucion) + '</p>' : '') +
        (propuesta.estado === 'pendiente' && puedeAprobar && propuesta.autor_id !== identidadId ? '<div class="mp-actions"><button data-resolver="' + propuesta.id + '" data-accion="aprobar">Aprobar</button><button data-resolver="' + propuesta.id + '" data-accion="rechazar">Rechazar</button></div>' : '') + '</article>';
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
      document.getElementById('mp-entrar').textContent = datos.nombre + ' / Cambiar identidad';
      document.getElementById('mp-contador').textContent = datos.pendientes + (datos.pendientes === 1 ? ' pendiente' : ' pendientes');
      estado.textContent = '';
      render();
    } catch (error) { estado.textContent = error.message; }
  }
  document.getElementById('mp-entrar').addEventListener('click', async function () { if (await window.identificarMangueras()) await cargar(); });
  document.getElementById('mp-actualizar').addEventListener('click', cargar);
  document.getElementById('mp-filtro').addEventListener('change', render);
  var resolucion = document.getElementById('mp-resolucion');
  lista.addEventListener('click', function (evento) {
    var boton = evento.target.closest('[data-resolver]');
    if (!boton) return;
    document.getElementById('mp-resolucion-form').dataset.id = boton.dataset.resolver;
    document.getElementById('mp-resolucion-form').dataset.accion = boton.dataset.accion;
    document.getElementById('mp-resolucion-titulo').textContent = (boton.dataset.accion === 'aprobar' ? 'Aprobar' : 'Rechazar') + ' propuesta #' + boton.dataset.resolver;
    document.getElementById('mp-resolucion-clave').value = '';
    document.getElementById('mp-resolucion-motivo').value = '';
    document.getElementById('mp-resolucion-error').textContent = '';
    resolucion.showModal();
  });
  document.getElementById('mp-resolucion-cancelar').addEventListener('click', function () { resolucion.close(); });
  resolucion.addEventListener('close', function () { document.getElementById('mp-resolucion-clave').value = ''; });
  document.getElementById('mp-resolucion-form').addEventListener('submit', async function (evento) {
    evento.preventDefault();
    var boton = evento.target.querySelector('[type=submit]');
    boton.disabled = true;
    try {
      var respuesta = await fetch('/api/mangueras/propuestas/' + evento.target.dataset.id + '/resolver', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
          operario_id: identidadId, clave: document.getElementById('mp-resolucion-clave').value,
          accion: evento.target.dataset.accion, motivo: document.getElementById('mp-resolucion-motivo').value
        })
      });
      document.getElementById('mp-resolucion-clave').value = '';
      var datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error);
      resolucion.close();
      await cargar();
    } catch (error) { document.getElementById('mp-resolucion-error').textContent = error.message; }
    finally { boton.disabled = false; }
  });
  cargar();
})();