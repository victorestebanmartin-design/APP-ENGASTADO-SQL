// mangueras.js — Preparación de Mangueras v1

(function () {
  'use strict';

  function badgeColor(codCable) {
    return (typeof getCodCableColor === 'function')
      ? getCodCableColor(codCable)
      : { bg: '#6b7280', text: '#fff' };
  }

  var mangueras = [];   // lista completa cargada
  var idx       = 0;   // índice actual
  var cortes    = [];   // cortes registrados disponibles
  var archivoActual = null;
  var ordenActual = null;
  var enviandoEscaneo = false;
  var segundosFichados = 0;
  var inicioReloj = 0;
  var relojActivo = false;

  function formatoCronometro(segundos) {
    var total = Math.max(0, Math.floor(segundos));
    var horas = Math.floor(total / 3600);
    var minutos = Math.floor(total % 3600 / 60);
    var resto = total % 60;
    return [horas, minutos, resto].map(function (valor) { return String(valor).padStart(2, '0'); }).join(':');
  }

  function pintarCronometro() {
    var reloj = document.getElementById('mg-cronometro');
    if (!reloj) return;
    var total = segundosFichados;
    if (relojActivo) total += Math.floor((Date.now() - inicioReloj) / 1000);
    reloj.textContent = formatoCronometro(total);
  }

  function mostrarTrabajo(preparacion, aviso) {
    document.getElementById('mg-trabajo').hidden = !ordenActual;
    var sinOrden = document.getElementById('mg-sin-orden');
    if (sinOrden) sinOrden.hidden = true;
    if (!ordenActual) return;
    document.getElementById('mg-orden').textContent = 'Orden ' + ordenActual.numero + ' / Cantidad ' + ordenActual.cantidad;
    segundosFichados = Math.max(0, Number(preparacion.segundos) || 0);
    inicioReloj = Date.now();
    relojActivo = preparacion.estado === 'en_preparacion';
    pintarCronometro();
    document.getElementById('mg-trabajo-resumen').textContent = (aviso ? '⚠ ' + aviso + ' — ' : '') +
      window.estadoMangueras(preparacion.estado) + ' / ' + preparacion.operarios.join(', ');
    document.getElementById('mg-trazabilidad').dataset.trazabilidadMangueras = ordenActual.id;
    document.getElementById('mg-pausar').disabled = preparacion.estado !== 'en_preparacion';
    document.getElementById('mg-terminar').disabled = preparacion.estado !== 'en_preparacion';
  }

  setInterval(pintarCronometro, 1000);

  async function actualizarTrabajo(accion, extra) {
    if (!ordenActual) return;
    var respuesta = await fetch('/api/mangueras/trabajo/' + encodeURIComponent(ordenActual.id), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ accion: accion }, extra))
    });
    var datos = await respuesta.json();
    if (!respuesta.ok) throw new Error(datos.error || 'No se pudo registrar el trabajo.');
    mostrarTrabajo(datos.preparacion);
    return datos;
  }

  document.getElementById('mg-pausar').addEventListener('click', async function () {
    try { await actualizarTrabajo('pausar'); abrirModalCorte(); }
    catch (error) { alert(error.message); }
  });
  document.getElementById('mg-terminar').addEventListener('click', async function () {
    if (!confirm('Marcar como terminada la preparacion de mangueras de esta orden?')) return;
    try { await actualizarTrabajo('terminar'); abrirModalCorte(); }
    catch (error) { alert(error.message); }
  });
  setInterval(function () {
    if (ordenActual && !document.getElementById('mg-pausar').disabled) {
      actualizarTrabajo('latido').catch(function (error) {
        document.getElementById('mg-trabajo-resumen').textContent = error.message;
        document.getElementById('mg-pausar').disabled = true;
        document.getElementById('mg-terminar').disabled = true;
        abrirModalCorte();
      });
    }
  }, 30000);
  window.addEventListener('pagehide', function () {
    if (!ordenActual) return;
    navigator.sendBeacon('/api/mangueras/trabajo/' + encodeURIComponent(ordenActual.id),
      new Blob([JSON.stringify({ accion: 'pausar' })], { type: 'application/json' }));
  });

  // ── Referencias DOM ──────────────────────────────────────────────────

  var divActivo   = document.getElementById('mg-activo');
  var lblCable    = document.getElementById('mg-cable-nombre');
  var lblContador = document.getElementById('mg-contador');
  var divInfo     = document.getElementById('mg-cable-info');
  var divObsRaw   = document.getElementById('mg-obs-raw');
  var divInst     = document.getElementById('mg-instrucciones');
  var btnPrev     = document.getElementById('btn-mg-prev');
  var btnNext     = document.getElementById('btn-mg-next');

  // Modal corte
  var modalCorte   = document.getElementById('modal-corte');
  var inputCorte   = document.getElementById('modal-input-corte');
  var errorCorte   = document.getElementById('modal-corte-error');
  var listaCorteEl = document.getElementById('modal-cortes-lista-contenido');

  // Banner corte actual
  var corteBanner  = document.getElementById('mg-corte-banner');
  var corteCodigoEl = document.getElementById('mg-corte-codigo');
  var corteDescEl   = document.getElementById('mg-corte-desc');

  // ── Modal de selección de corte ──────────────────────────────────────
  function mostrarVistaCorte(vista) {
    ['metodo', 'input', 'lista'].forEach(function (v) {
      var el = document.getElementById('modal-corte-' + v);
      if (el) el.classList.toggle('hidden', v !== vista);
    });
    if (vista === 'input') {
      setTimeout(function () { if (inputCorte) inputCorte.focus(); }, 50);
    }
  }

  function abrirModalCorte() {
    mostrarVistaCorte('metodo');
    if (modalCorte) modalCorte.classList.remove('hidden');
  }

  function cerrarModalCorte() {
    if (modalCorte) modalCorte.classList.add('hidden');
  }

  function mostrarInputCorte() {
    if (errorCorte) errorCorte.classList.add('hidden');
    if (inputCorte) inputCorte.value = '';
    mostrarVistaCorte('input');
  }

  function mostrarListaCortes() {
    mostrarVistaCorte('lista');
    listaCorteEl.innerHTML = '<p class="modal-bonos-cargando">Cargando cortes...</p>';

    if (cortes.length === 0) {
      listaCorteEl.innerHTML = '<p class="modal-bonos-vacio">No hay cortes registrados.</p>';
      return;
    }

    listaCorteEl.innerHTML = cortes.map(function (c) {
      var desc = c.descripcion || c.proyecto || '';
      return '<div class="modal-bono-item" data-codigo="' + esc(c.codigo) + '">' +
               '<div>' +
                 '<div class="modal-bono-item-nombre">' + esc(c.codigo) + '</div>' +
                 (desc ? '<div class="modal-bono-item-fecha">' + esc(desc) + '</div>' : '') +
               '</div>' +
               '<span class="modal-bono-item-arrow">▶</span>' +
             '</div>';
    }).join('');

    Array.prototype.forEach.call(
      listaCorteEl.querySelectorAll('.modal-bono-item'),
      function (item) {
        item.addEventListener('click', function () {
          seleccionarCorte(item.getAttribute('data-codigo'));
        });
      }
    );
  }

  async function confirmarCorteCodigo() {
    if (enviandoEscaneo) return;
    var valor = inputCorte ? inputCorte.value.trim() : '';
    if (!valor) {
      if (errorCorte) errorCorte.classList.remove('hidden');
      if (inputCorte) inputCorte.focus();
      return;
    }
    enviandoEscaneo = true;
    document.getElementById('btn-corte-confirmar').disabled = true;
    try {
      var respuesta = await fetch('/api/mangueras/trabajo/escanear', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codigo: valor })
      });
      var datos = await respuesta.json();
      if (!respuesta.ok) throw new Error(datos.error || 'No se pudo registrar la orden.');
      ordenActual = datos.orden;
      mostrarTrabajo(datos.preparacion, datos.aviso);
      cerrarModalCorte();
      await cargarMangueras(datos.corte);
    } catch (error) {
      errorCorte.textContent = error.message;
      errorCorte.classList.remove('hidden');
    } finally {
      enviandoEscaneo = false;
      document.getElementById('btn-corte-confirmar').disabled = false;
    }
  }

  async function seleccionarCorte(codigo) {
    try {
      if (ordenActual && !document.getElementById('mg-pausar').disabled) await actualizarTrabajo('pausar');
    } catch (error) { alert(error.message); return; }
    ordenActual = null;
    document.getElementById('mg-trabajo').hidden = true;
    var cod = String(codigo || '').trim();
    var corte = cortes.find(function (c) {
      return String(c.codigo).toUpperCase() === cod.toUpperCase();
    });

    if (!corte) {
      if (errorCorte) {
        errorCorte.textContent = 'El código "' + cod + '" no está registrado.';
        errorCorte.classList.remove('hidden');
      }
      mostrarVistaCorte('input');
      if (inputCorte) { inputCorte.value = cod; inputCorte.focus(); }
      return;
    }

    cerrarModalCorte();
    cargarMangueras(corte);
  }

  function actualizarBanner(corte) {
    if (!corteBanner) return;
    var desc = corte.descripcion || corte.proyecto || '';
    corteCodigoEl.textContent = corte.codigo;
    corteDescEl.textContent = desc;
    corteBanner.classList.add('activo');
    // Entrar por la lista de cortes no trae orden: sin ella no hay reloj ni
    // «Terminar preparación», y la orden no podría ir a un carro.
    var sinOrden = document.getElementById('mg-sin-orden');
    if (sinOrden) {
      sinOrden.hidden = !!ordenActual;
      sinOrden.dataset.corte = corte.codigo;
    }
  }

  var btnEscanearOrden = document.getElementById('mg-escanear-orden');
  if (btnEscanearOrden) btnEscanearOrden.addEventListener('click', function () {
    mostrarInputCorte();
    inputCorte.value = document.getElementById('mg-sin-orden').dataset.corte + '-';
    abrirModalCorte();
    mostrarVistaCorte('input');
  });

  // ── Cargar lista de cortes registrados ───────────────────────────────
  async function cargarListaCortes() {
    try {
      var resp = await fetch('/api/codigos_cortes/listar');
      var data = await resp.json();
      cortes = (data.success && data.codigos) ? data.codigos : [];
    } catch (e) {
      console.error('Error cargando cortes:', e);
      cortes = [];
    }
  }

  // ── Cargar mangueras del corte ───────────────────────────────────────
  async function cargarMangueras(corte) {
    var archivo = corte && corte.archivo ? corte.archivo : null;
    if (!archivo) { abrirModalCorte(); return; }


    try {
      var resp = await fetch('/api/mangueras/datos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archivo: archivo })
      });
      var data = await resp.json();

      if (!data.success) {
        if (ordenActual) await actualizarTrabajo('pausar');
        alert('Error: ' + (data.error || 'Error desconocido'));
        abrirModalCorte();
        return;
      }

      mangueras = data.mangueras || [];
      if (mangueras.length === 0) {
        if (ordenActual) await actualizarTrabajo('pausar');
        alert('No se encontraron filas con instrucciones de pelado (<-) en este corte.');
        abrirModalCorte();
        return;
      }

      idx = 0;
      archivoActual = archivo;
      actualizarBanner(corte);
      divActivo.style.display = 'block';
      renderManguera();

    } catch (e) {
      if (ordenActual) actualizarTrabajo('pausar').catch(function () {});
      alert('Error de conexión: ' + e.message);
      abrirModalCorte();
    }
  }

  // Botón cambiar corte del banner
  var btnCambiarCorte = document.getElementById('mg-corte-cambiar');
  if (btnCambiarCorte) btnCambiarCorte.addEventListener('click', async function () {
    try {
      if (ordenActual && !document.getElementById('mg-pausar').disabled) await actualizarTrabajo('pausar');
      abrirModalCorte();
    } catch (error) { alert(error.message); }
  });
  document.addEventListener('mangueras-pendientes-actualizadas', async function () {
    if (!archivoActual || document.querySelector('dialog[open]')) return;
    var archivo = archivoActual;
    var fila = mangueras[idx] && mangueras[idx].fila_excel;
    try {
      var respuesta = await fetch('/api/mangueras/datos', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archivo: archivo })
      });
      var datos = await respuesta.json();
      if (archivo !== archivoActual || !datos.success || !datos.mangueras.length) return;
      mangueras = datos.mangueras;
      var posicion = mangueras.findIndex(function (manguera) { return manguera.fila_excel === fila; });
      idx = posicion >= 0 ? posicion : 0;
      renderManguera();
    } catch (error) { console.error('No se pudo actualizar la preparacion:', error); }
  });
  var btnEditar = document.getElementById('mg-editar');
  if (btnEditar) btnEditar.addEventListener('click', async function () {
    var manguera = mangueras[idx];
    if (!manguera || !archivoActual) return;
    var archivo = archivoActual;
    var fila = manguera.fila_excel;
    btnEditar.disabled = true;
    try {
      if (await window.identificarMangueras()) {
        window.location.href = '/mangueras/editor?' + new URLSearchParams({ proponer: '1', archivo: archivo, fila: fila });
      }
    } catch (error) { alert(error.message); }
    finally { btnEditar.disabled = false; }
  });

  // Wiring botones modal
  document.getElementById('btn-corte-input').addEventListener('click', mostrarInputCorte);
  document.getElementById('btn-corte-lista').addEventListener('click', mostrarListaCortes);
  document.getElementById('btn-corte-volver1').addEventListener('click', function () { mostrarVistaCorte('metodo'); });
  document.getElementById('btn-corte-volver2').addEventListener('click', function () { mostrarVistaCorte('metodo'); });
  document.getElementById('btn-corte-confirmar').addEventListener('click', confirmarCorteCodigo);
  if (inputCorte) {
    inputCorte.addEventListener('keypress', function (e) {
      if (e.key === 'Enter') confirmarCorteCodigo();
    });
  }

  // ── Renderizar manguera actual ────────────────────────────────────────
  function renderManguera() {
    var mg = mangueras[idx];
    if (!mg) return;

    // Cabecera — trío: marca · paquete · elemento
    lblCable.textContent = mg.cable_marca || '—';

    var badgeEl = document.getElementById('mg-paquete-badge');
    if (badgeEl) {
      if (mg.numero_etiqueta) {
        var c = badgeColor(mg.cod_cable);
        badgeEl.innerHTML = '<span class="mg-paquete-badge" style="background:' + c.bg +
          ';color:' + c.text + ';">🏷 #' + mg.numero_etiqueta + '</span>';
      } else {
        badgeEl.innerHTML = '';
      }
    }

    var elemEl = document.getElementById('mg-elemento');
    if (elemEl) elemEl.textContent = mg.de_elemento || '';

    lblContador.textContent = (idx + 1) + ' / ' + mangueras.length;

    // Info cable (terminales) — ocultar si no hay nada
    var infoHtmlStr = infoHtml(mg);
    divInfo.innerHTML = infoHtmlStr;
    divInfo.style.display = infoHtmlStr.trim() ? 'flex' : 'none';

    // Obs raw
    divObsRaw.textContent = mg.observaciones_raw || '';
    var obsMangueras = document.getElementById('mg-obs-mangueras');
    if (obsMangueras) {
      obsMangueras.textContent = mg.observaciones_mangueras || '';
      obsMangueras.style.display = obsMangueras.textContent ? 'block' : 'none';
    }
    var avisoMangueras = document.getElementById('mg-aviso-mangueras');
    if (avisoMangueras) {
      avisoMangueras.textContent = mg.aviso_mangueras || '';
      avisoMangueras.style.display = avisoMangueras.textContent ? 'block' : 'none';
    }

    // Instrucciones
    var propuestaPendiente = (mg.propuestas || [])[0];
    divInst.innerHTML = propuestaPendiente ? ['de', 'para'].map(function (lado) {
      return '<div class="lado-card lado-' + lado + '"><div class="lado-title">' +
        (lado === 'de' ? 'Lado De · liso (sin guion)' : 'Lado Para · guion') + '</div>' +
        window.medidasMangueraHtml(mg, propuestaPendiente.sugerido, lado, false) + '</div>';
    }).join('') : instruccionesHtml(mg);
    document.getElementById('mg-propuestas').innerHTML = (mg.propuestas || []).map(function (propuesta) {
      return '<section class="mp-pendiente"><strong>Manguera pendiente de confirmar. Entre () medidas sugeridas.</strong>' +
        '<p>' + esc(propuesta.autor + ' · ' + propuesta.fecha) + '</p><p>Motivo: ' + esc(propuesta.motivo) + '</p></section>';
    }).join('');
    if (propuestaPendiente && obsMangueras && (mg.observaciones_mangueras || '') !== (propuestaPendiente.sugerido.observaciones_mangueras || '')) {
      obsMangueras.textContent = (mg.observaciones_mangueras || 'Sin observaciones') + ' (' + (propuestaPendiente.sugerido.observaciones_mangueras || 'Sin observaciones') + ')';
      obsMangueras.style.display = 'block';
    }

    // Botones nav
    btnPrev.disabled = (idx === 0);
    btnNext.disabled = (idx === mangueras.length - 1);
  }

  function infoHtml(mg) {
    var html = '';
    var deOk   = mg.de_terminal   && mg.de_terminal   !== 'S/T';
    var paraOk = mg.para_terminal && mg.para_terminal !== 'S/T';
    if (deOk) {
      html += itemInfo('De Terminal', mg.de_terminal);
    }
    if (deOk && paraOk) {
      html += '<div class="info-arrow">→</div>';
    }
    if (paraOk) {
      html += itemInfo('Para Terminal', mg.para_terminal);
    }
    return html;
  }

  function itemInfo(label, val) {
    return '<div class="info-item">' +
             '<span class="info-label">' + esc(label) + '</span>' +
             '<span class="info-val">' + esc(val) + '</span>' +
           '</div>';
  }

  function instruccionesHtml(mg) {
    var html = '';
    html += ladoHtml(mg.de,   '← Lado De · liso (sin guion)',   'lado-de',   mg.retractil_de   || []);
    html += ladoHtml(mg.para, 'Lado Para · guion →', 'lado-para', mg.retractil_para || []);
    return html;
  }

  function ladoHtml(inst, titulo, clase, retractiles) {
    retractiles = retractiles || [];
    if (!inst && retractiles.length === 0) {
      return '<div class="lado-card lado-vacio">' +
               '<div class="lado-title">⬜ ' + titulo + '</div>' +
               '<div style="color:#d1d5db; font-size:14px;">Sin instrucciones</div>' +
             '</div>';
    }

    var rows = '';
    var pmVal = inst ? inst.pm : null;  // puede ser null si no se especificó

    if (inst) {
    // PM (pelado manguera)
    rows += instFila('Pelado Manguera',
      pmVal !== null && pmVal !== undefined
        ? '<span class="inst-val val-pm">' + pmVal + '</span><span class="inst-unit">mm</span>'
        : '<span class="val-dash">—</span>');

    // Malla: si no se especifica, queda a la misma longitud que el pelado de manguera
    if (inst.m_cortar) {
      rows += instFila('Malla',
        '<span class="inst-val val-cortar">✂ CORTAR</span>');
    } else if (inst.m_mrs) {
      rows += instFila('Malla',
        (inst.m_mrs_medida !== null && inst.m_mrs_medida !== undefined
          ? '<span class="inst-val val-malla">' + inst.m_mrs_medida + '</span><span class="inst-unit">mm</span> '
          : '') +
        '<span class="inst-val" style="color:#b45309;">↩ Hacia atrás</span>' +
        '<span style="font-size:10px;color:#9ca3af;margin-left:6px;">sin retráctil</span>');
    } else if (inst.m_mrc) {
      var mrcMedida = inst.m_mrc_medida;
      rows += instFila('Malla',
        (mrcMedida !== null && mrcMedida !== undefined
          ? '<span class="inst-val val-malla">' + mrcMedida + '</span><span class="inst-unit">mm</span> '
          : '') +
        '<span style="color:#b45309; font-weight:700;">↩ Hacia atrás</span>' +
        '<span style="font-size:10px;color:#9ca3af;margin-left:6px;">con retráctil</span>');
    } else if (inst.m !== null && inst.m !== undefined) {
      rows += instFila('Pelado Malla',
        '<span class="inst-val val-malla">' + inst.m + '</span><span class="inst-unit">mm</span>');
    } else {
      // Sin instrucción de malla → igual que el pelado de manguera
      rows += instFila('Pelado Malla',
        pmVal !== null && pmVal !== undefined
          ? '<span class="inst-val val-malla" title="Igual que pelado de manguera">' + pmVal + '</span>' +
            '<span class="inst-unit">mm</span>' +
            '<span style="font-size:10px;color:#9ca3af;margin-left:4px;">(= manguera)</span>'
          : '<span class="val-dash">—</span>');
    }

    // Activos: si no se especifica, quedan a la medida del pelado de manguera
    if (inst.a_todos !== null && inst.a_todos !== undefined) {
      rows += instFila('Activos (todos)',
        '<span class="inst-val val-activo">' + inst.a_todos + '</span><span class="inst-unit">mm</span>');
    } else if (inst.a_especificos && Object.keys(inst.a_especificos).length > 0) {
      var keys = Object.keys(inst.a_especificos).sort(function (a, b) { return +a - +b; });
      keys.forEach(function (k) {
        rows += instFila('Activo ' + k,
          '<span class="inst-val val-activo">' + inst.a_especificos[k] + '</span><span class="inst-unit">mm</span>');
      });
    } else {
      // Sin instrucción de activos → quedan a la medida del pelado de manguera
      rows += instFila('Activos',
        pmVal !== null && pmVal !== undefined
          ? '<span class="inst-val val-activo" title="Igual que pelado de manguera">' + pmVal + '</span>' +
            '<span class="inst-unit">mm</span>' +
            '<span style="font-size:10px;color:#9ca3af;margin-left:4px;">(= manguera)</span>'
          : '<span class="val-dash">—</span>');
    }
    } // fin if (inst)

    // Retráctiles
    if (retractiles.length > 0) {
      retractiles.forEach(function(r) {
        rows += instFila('Retráctil ' + esc(r.codigo),
          '<span class="inst-val val-retractil">' + r.medida + '</span><span class="inst-unit">mm</span>');
      });
    }

    return '<div class="lado-card ' + clase + '">' +
             '<div class="lado-title">' + titulo + '</div>' +
             rows +
           '</div>';
  }

  function instFila(label, valHtml) {
    return '<div class="inst-row">' +
             '<span class="inst-label">' + esc(label) + '</span>' +
             '<span>' + valHtml + '</span>' +
           '</div>';
  }

  // ── Navegación y gestos táctiles ─────────────────────────────────────
  btnPrev.addEventListener('click', function () { if (idx > 0) { idx--; renderManguera(); } });
  btnNext.addEventListener('click', function () { if (idx < mangueras.length - 1) { idx++; renderManguera(); } });
  // Swipe izquierda → siguiente, swipe derecha → anterior
  var _swTx = 0;
  divActivo.addEventListener('touchstart', function (e) { _swTx = e.changedTouches[0].clientX; }, { passive: true });
  divActivo.addEventListener('touchend', function (e) {
    if (mangueras.length === 0) return;
    var dx = e.changedTouches[0].clientX - _swTx;
    if (Math.abs(dx) < 60) return;
    if (dx < 0 && idx < mangueras.length - 1) { idx++; renderManguera(); }
    else if (dx > 0 && idx > 0) { idx--; renderManguera(); }
  }, { passive: true });

  document.addEventListener('keydown', function (e) {
    if (mangueras.length === 0) return;
    if (document.querySelector('dialog[open]')) return;
    if (['INPUT', 'SELECT', 'TEXTAREA'].indexOf(e.target.tagName) !== -1) return;
    if (e.key === 'ArrowLeft'  && idx > 0)                        { idx--; renderManguera(); }
    if (e.key === 'ArrowRight' && idx < mangueras.length - 1)     { idx++; renderManguera(); }
    if ((e.key === 'Enter' || e.key === ' ') && idx < mangueras.length - 1) {
      e.preventDefault();
      idx++;
      renderManguera();
    }
  });

  // ── Utilidades ────────────────────────────────────────────────────────
  function esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // ── Init ─────────────────────────────────────────────────────────────
  if (typeof initCableColors === 'function') initCableColors();
  cargarListaCortes();
  abrirModalCorte();
  setInterval(function () {
    if (document.visibilityState === 'visible') {
      fetch('/api/sesion/operario/latido', { method: 'POST' }).catch(function () {});
    }
  }, 60000);

  // Puesto olvidado: tras unos minutos sin tocarlo se cierra la sesión, y el
  // tiempo sin actividad no cuenta como preparación.
  if (window.inactividadOperario) window.inactividadOperario.iniciar({
    antesDeSalir: async function (inactivoSegundos) {
      if (!document.getElementById('mg-pausar').disabled) {
        await actualizarTrabajo('pausar', { inactivo_segundos: inactivoSegundos });
      }
    }
  });

})();
