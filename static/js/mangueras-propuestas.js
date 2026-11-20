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
        // En el menú de Admin el número va en una pastilla aparte (y se oculta si es 0).
        var numero = elemento.querySelector('[data-contador-numero]');
        if (numero) { numero.textContent = datos.pendientes; numero.hidden = !datos.pendientes; return; }
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

  // ── Pantalla de Propuestas de mangueras (lista común en propuestas-lista.js)
  if (!document.getElementById('ep-lista') || !window.listaPropuestas) return;

  // Cada cambio de la propuesta con su fila tal como estaba y como se propone
  function cambiosDe(p) {
    return p.sugerido.cambios.map(function (cambio) {
      return {
        original: p.original.find(function (fila) { return fila.fila === cambio.fila; }) || { fila: cambio.fila },
        sugerido: p.sugerido.filas.find(function (fila) { return fila.fila === cambio.fila; }) || {}
      };
    });
  }

  window.listaPropuestas({
    api: '/api/mangueras/propuestas',
    columnas: 7,
    estados: ['pendiente', 'aprobada', 'rechazada', 'restaurada'],
    claveAviso: 'mangueras-propuestas-resueltas',
    alResolver: function () { actualizarContadores(true); },
    aprobar: { boton: 'Aceptar', hecho: 'Aceptó ', verbos: { gerundio: 'Aceptando', hecho: 'aceptada', hechos: 'aceptadas' } },
    ayudaAprobar: 'Aceptar: se aplica al Excel del corte',
    ayudaRechazar: 'Rechazar: la preparación sigue como está',
    deshacer: {
      accion: 'restaurar', boton: 'Restaurar', etiqueta: 'Restauró',
      ayuda: 'La manguera vuelve a como estaba antes de la propuesta (se guarda copia del Excel)',
      verbos: { gerundio: 'Restaurando', hecho: 'restaurada', hechos: 'restauradas' },
      campos: { at: 'restaurada_at', por: 'restaurada_por_nombre', motivo: 'motivo_restauracion' }
    },
    mensajes: {
      aprobar: 'La nueva preparación ya está aplicada al corte.',
      restaurar: 'Regenera las etiquetas del corte para que engastado lo vea.'
    },
    buscar: function (p) {
      return cambiosDe(p).map(function (c) {
        var o = c.original;
        return [o.paquete, o.cable_marca, o.cod_cable, o.de_elemento].join(' ');
      }).join(' ');
    },
    celdas: function (p, h) {
      var esc = h.esc;
      var cambios = cambiosDe(p);
      var paquetes = cambios.map(function (c) { return c.original.paquete; })
        .filter(function (n, i, todos) { return n && todos.indexOf(n) === i; });
      var detalle = cambios.map(function (c) {
        var o = c.original;
        return '<div class="ep-cambio"><h4>' + (o.paquete ? '<span class="extra">Paq ' + esc(o.paquete) + ' · </span>' : '') +
          esc(o.cable_marca || '') + ' <span class="extra">· ' + esc(o.cod_cable || '') + ' · ' + esc(o.de_elemento || '') +
          ' · fila ' + esc(o.fila) + '</span></h4>' + window.comparacionMangueras(o, c.sugerido) + '</div>';
      }).join('');
      return '<td class="ep-term ep-corte">' + esc(p.archivo) +
        (paquetes.length ? '<small>Paquete ' + esc(paquetes.join(', ')) + '</small>' : '') +
        '<small>' + cambios.length + (cambios.length === 1 ? ' manguera' : ' mangueras') + '</small></td>' +
        '<td class="ep-celda-cambios">' + detalle + '</td>';
    }
  });
})();