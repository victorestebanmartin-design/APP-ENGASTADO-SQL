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

  // ── Pantalla de Propuestas de engastado (lista común en propuestas-lista.js)
  if (!document.getElementById('ep-lista') || !window.listaPropuestas) return;

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
  function numerosPaquete(p) {
    return p.cables.map(function (c) { return c.paquete; })
      .filter(function (n, i, todos) { return n && todos.indexOf(n) === i; });
  }

  window.listaPropuestas({
    api: '/api/engastado/propuestas',
    columnas: 7,
    estados: ['pendiente', 'aprobada', 'rechazada', 'revertida'],
    claveAviso: 'engastado-propuestas-resueltas',
    alResolver: actualizarContadores,
    ayudaAprobar: 'Aprobar: el terminal deja de pedirse',
    ayudaRechazar: 'Rechazar: el Excel no cambia',
    deshacer: {
      accion: 'revertir', boton: 'Revertir', etiqueta: 'Revirtió',
      ayuda: 'El terminal se vuelve a pedir en esos cables',
      verbos: { gerundio: 'Revirtiendo', hecho: 'revertida', hechos: 'revertidas' },
      campos: { at: 'revertida_at', por: 'revertida_por', motivo: 'motivo_reversion' }
    },
    mensajes: {
      aprobar: 'El terminal ya no se pide en esos cables.',
      revertir: 'El terminal se vuelve a pedir.'
    },
    buscar: function (p) {
      return [p.terminal, p.paquete, numerosPaquete(p).join(' ')].concat(p.cables.map(function (c) {
        return [c.cable_marca, c.cod_cable, c.elemento, c.serie].join(' ');
      })).join(' ');
    },
    celdas: function (p, h) {
      var esc = h.esc;
      var numeros = numerosPaquete(p);
      var cables = p.cables.map(function (c) {
        return '<li>' + (c.paquete ? '<span class="extra">Paq ' + esc(c.paquete) + ' · </span>' : '') +
          '<span class="marca">' + esc(c.cable_marca) + '</span>' +
          ' <span class="extra">· ' + esc(c.elemento) + (c.serie ? ' · ' + esc(c.serie) : '') +
          ' · ' + (c.lado === 'de' ? 'De (liso)' : 'Para (guion)') +
          (c.archivo !== p.archivo ? ' · ' + esc(c.archivo) : '') + (c.fila ? ' · fila ' + c.fila : '') + '</span>' +
          (c.resultado ? ' <span class="res">— ' + esc(textoResultado(c.resultado)) + '</span>' : '') + '</li>';
      }).join('');
      return '<td class="ep-term">' + esc(p.terminal) +
        '<small>' + (numeros.length ? 'Paquete ' + esc(numeros.join(', ')) + ' · ' : '') + esc(p.paquete) + '</small>' +
        '<small>' + esc(p.archivo) + '</small></td>' +
        '<td><ul class="ep-cables">' + cables + '</ul></td>';
    }
  });
})();