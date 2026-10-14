(function () {
  'use strict';
  window.estadoMangueras = function (estado) {
    return { en_preparacion: 'En preparacion', pausada: 'Pausada', terminada: 'Terminada' }[estado] || estado;
  };
  window.duracionMangueras = function (segundos) {
    return Math.floor(segundos / 3600) + ' h ' + Math.floor(segundos % 3600 / 60) + ' min ' + segundos % 60 + ' s';
  };
  function fecha(valor) {
    return valor ? new Date(valor).toLocaleString('es-ES', { timeZone: 'Europe/Madrid' }) : 'Sin finalizar';
  }
  document.addEventListener('click', async function (evento) {
    var boton = evento.target.closest('[data-trazabilidad-mangueras]');
    if (!boton) return;
    var dialogo = document.createElement('dialog');
    dialogo.style.cssText = 'box-sizing:border-box;max-width:900px;width:calc(100% - 32px);max-height:85vh;overflow:auto;border:1px solid #64748b;border-radius:8px;padding:20px;color:#20252a;background:#fff;';
    var titulo = document.createElement('h2');
    titulo.textContent = 'Preparacion de mangueras';
    titulo.style.cssText = 'font-size:20px;margin:0 0 16px;';
    var cerrar = document.createElement('button');
    cerrar.type = 'button';
    cerrar.textContent = 'Cerrar';
    cerrar.addEventListener('click', function () { dialogo.close(); });
    dialogo.addEventListener('close', function () { dialogo.remove(); });
    var contenido = document.createElement('div');
    contenido.textContent = 'Cargando...';
    dialogo.append(titulo, contenido, cerrar);
    document.body.appendChild(dialogo);
    dialogo.showModal();
    try {
      var respuesta = await fetch('/api/mangueras/trabajo/' + encodeURIComponent(boton.dataset.trazabilidadMangueras));
      var datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error || 'No se pudo consultar la preparacion.');
      var preparacion = datos.preparacion;
      contenido.replaceChildren();
      var resumen = document.createElement('p');
      resumen.textContent = preparacion.inicio ? 'Inicio: ' + fecha(preparacion.inicio) + ' / Fin: ' + fecha(preparacion.fin) +
        ' / ' + window.estadoMangueras(preparacion.estado) + ' / Tiempo acumulado de operarios: ' + window.duracionMangueras(preparacion.segundos) : 'Sin preparacion registrada.';
      contenido.appendChild(resumen);
      preparacion.tramos.forEach(function (tramo) {
        var fila = document.createElement('p');
        fila.style.cssText = 'border-top:1px solid #d1d5db;padding:12px 0;overflow-wrap:anywhere;';
        fila.textContent = tramo.operario_nombre + ' / Inicio: ' + fecha(tramo.inicio) + ' / Fin: ' +
          (tramo.fin ? fecha(tramo.fin) : 'En curso') + ' / ' + window.duracionMangueras(tramo.segundos);
        contenido.appendChild(fila);
      });
    } catch (error) { contenido.textContent = error.message; }
  });
})();