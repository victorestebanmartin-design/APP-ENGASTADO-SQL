/**
 * inactividad-operario.js -- Cierra la sesión de un puesto que alguien dejó abierto.
 *
 * Mangueras y manguitos mandan un latido para que el login no caduque mientras
 * la página está abierta, así que un PC olvidado seguiría "dentro" con la
 * tarjeta del último operario. Aquí se vigila la actividad real (clic, tecla,
 * ratón, táctil): tras TIEMPO_INACTIVO sin nada sale un aviso con cuenta atrás y,
 * si nadie lo atiende, se cierra la sesión y se vuelve al lector de tarjetas.
 *
 * `antesDeSalir(segundosInactivo)` deja a la página pausar su reloj de trabajo
 * descontando la inactividad, para que esos minutos no cuenten como trabajo.
 */
(function () {
  'use strict';

  var TIEMPO_INACTIVO = 5 * 60 * 1000;
  var CUENTA_ATRAS = 20;

  window.inactividadOperario = {
    iniciar: function (opciones) {
      var antesDeSalir = (opciones && opciones.antesDeSalir) || null;
      var ultimaActividad = Date.now();
      var aviso = null;
      var restante = 0;
      var cuenta = null;
      var saliendo = false;

      function ocultarAviso() {
        if (cuenta) { clearInterval(cuenta); cuenta = null; }
        if (aviso) { aviso.remove(); aviso = null; }
      }

      async function salir() {
        if (saliendo) return;
        saliendo = true;
        var inactivo = Math.max(0, Math.round((Date.now() - ultimaActividad) / 1000));
        try { if (antesDeSalir) await antesDeSalir(inactivo); } catch (_) { /* sale igualmente */ }
        try { await fetch('/api/sesion/operario/salir', { method: 'POST' }); } catch (_) { /* el gate de /login pedirá tarjeta */ }
        window.location.href = '/login';
      }

      function mostrarAviso() {
        restante = CUENTA_ATRAS;
        aviso = document.createElement('div');
        aviso.setAttribute('role', 'alertdialog');
        aviso.style.cssText = 'position:fixed;inset:0;z-index:100000;display:flex;align-items:center;justify-content:center;' +
          'background:rgba(0,0,0,.65);padding:16px;';
        aviso.innerHTML =
          '<div style="background:#fff;color:#1f2937;border-radius:14px;max-width:420px;width:100%;padding:28px;text-align:center;' +
          'box-shadow:0 20px 50px rgba(0,0,0,.4);font-family:system-ui,sans-serif;">' +
          '<div style="font-size:42px;line-height:1;">⏳</div>' +
          '<h2 style="margin:10px 0 6px;font-size:20px;">¿Sigues ahí?</h2>' +
          '<p style="margin:0 0 18px;font-size:15px;color:#4b5563;">Llevas un rato sin tocar la pantalla. ' +
          'La sesión se cerrará en <b id="inact-restante" style="font-size:20px;color:#b42318;">' + restante + '</b> s.</p>' +
          '<button type="button" id="inact-seguir" style="background:#0891b2;color:#fff;border:none;border-radius:8px;' +
          'padding:12px 26px;font-size:16px;font-weight:700;cursor:pointer;">Seguir trabajando</button></div>';
        document.body.appendChild(aviso);
        aviso.querySelector('#inact-seguir').addEventListener('click', actividad);
        aviso.querySelector('#inact-seguir').focus();
        cuenta = setInterval(function () {
          restante -= 1;
          var el = document.getElementById('inact-restante');
          if (el) el.textContent = Math.max(restante, 0);
          if (restante <= 0) { clearInterval(cuenta); cuenta = null; salir(); }
        }, 1000);
      }

      // Con el aviso en pantalla un roce del ratón no basta: hay que pulsar el
      // botón o una tecla, para que una vibración no mantenga abierto el puesto.
      function actividad(evento) {
        if (saliendo) return;
        if (aviso && evento && evento.type === 'mousemove') return;
        ultimaActividad = Date.now();
        ocultarAviso();
      }

      ['mousemove', 'mousedown', 'keydown', 'touchstart', 'wheel', 'scroll'].forEach(function (nombre) {
        document.addEventListener(nombre, actividad, { passive: true, capture: true });
      });

      setInterval(function () {
        if (!aviso && !saliendo && Date.now() - ultimaActividad >= TIEMPO_INACTIVO) mostrarAviso();
      }, 5000);
    }
  };
})();
