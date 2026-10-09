(function () {
  'use strict';

  var datos = null;
  var fuente = null;
  var originales = [];
  var cambios = new Map();
  var indice = 0;
  var ocupado = false;
  var pendiente = false;
  var cortesDisponibles = [];
  var copiaDescargada = false;
  var form = document.getElementById('me-form');
  var status = document.getElementById('me-status');
  var download = document.getElementById('me-download');
  var dialogo = document.getElementById('me-save-dialog');
  var destino = document.getElementById('me-destino');
  var estadoGuardado = document.getElementById('me-save-status');
  var pinForm = document.getElementById('me-pin-form');

  function mensajeGuardado(texto, error) {
    estadoGuardado.textContent = texto;
    estadoGuardado.classList.toggle('me-error', !!error);
  }

  function esc(valor) {
    return String(valor == null ? '' : valor).replace(/[&<>"']/g, function (caracter) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[caracter];
    });
  }

  function mensaje(texto, error) {
    status.textContent = texto;
    status.classList.toggle('me-error', !!error);
  }

  function claveBorrador() { return 'mangueras-editor:' + datos.revision; }

  function persistir() {
    document.getElementById('me-draft').textContent = cambios.size + ' mangueras modificadas';
    try { localStorage.setItem(claveBorrador(), JSON.stringify(Array.from(cambios.values()))); }
    catch (error) { mensaje('El navegador no puede guardar el borrador. Descarga el Excel antes de salir.', true); }
  }

  function cuerpo() {
    var body = new FormData();
    if (fuente.file) body.append('excel', fuente.file);
    else body.append('archivo', fuente.archivo);
    return body;
  }

  function bloquear(activo) {
    ocupado = activo;
    download.disabled = activo || !datos;
    document.getElementById('me-file').disabled = activo;
    document.getElementById('me-load').disabled = activo;
    document.getElementById('me-corte').disabled = activo;
    document.getElementById('me-workspace').inert = activo;
    dialogo.querySelectorAll('button, input, select').forEach(function (elemento) { elemento.disabled = activo; });
    document.getElementById('me-save-apply').disabled = activo || !destino.value;
  }

  async function cargar(nuevaFuente) {
    if (ocupado || !guardarActual()) return;
    fuente = nuevaFuente;
    bloquear(true);
    mensaje('Abriendo Excel...');
    try {
      var respuesta = await fetch('/api/mangueras/editor/leer', { method: 'POST', body: cuerpo() });
      if (respuesta.redirected) throw new Error('La sesión ha caducado. Vuelve a entrar en mangueras.');
      var resultado = await respuesta.json();
      if (!respuesta.ok || !resultado.success) throw new Error(resultado.error || 'No se pudo abrir el Excel.');
      datos = resultado;
      originales = structuredClone(datos.filas);
      cambios = new Map();
      try {
        var borrador = JSON.parse(localStorage.getItem(claveBorrador()) || '[]');
        borrador.forEach(function (fila) {
          var posicion = datos.filas.findIndex(function (actual) { return actual.fila === fila.fila; });
          if (posicion >= 0) {
            datos.filas[posicion] = Object.assign(datos.filas[posicion], fila);
            cambios.set(fila.fila, fila);
          }
        });
      } catch (error) { mensaje('No se pudo recuperar el borrador local.', true); }
      indice = 0;
      pendiente = false;
      document.getElementById('me-search').value = '';
      document.getElementById('me-name').textContent = datos.nombre + ' / ' + datos.hoja;
      document.getElementById('me-workspace').hidden = datos.filas.length === 0;
      persistir();
      renderLista();
      renderActual();
      mensaje(datos.filas.length ? (cambios.size ? 'Borrador recuperado.' : datos.filas.length + ' mangueras disponibles.') : 'No hay secciones Nx ni instrucciones de mangueras en este Excel.');
    } catch (error) {
      datos = null;
      fuente = null;
      document.getElementById('me-workspace').hidden = true;
      document.getElementById('me-name').textContent = 'Ningún Excel abierto';
      document.getElementById('me-draft').textContent = '';
      mensaje(error.message, true);
    } finally { bloquear(false); }
  }

  function renderLista() {
    if (!datos) return;
    var busqueda = document.getElementById('me-search').value.toLocaleLowerCase();
    document.getElementById('me-total').textContent = '(' + datos.filas.length + ')';
    document.getElementById('me-list').innerHTML = datos.filas.map(function (fila, posicion) {
      var identidad = [fila.cable_marca, fila.cod_cable, fila.de_elemento, fila.para_elemento, fila.seccion].join(' ');
      if (identidad.toLocaleLowerCase().indexOf(busqueda) < 0) return '';
      return '<button type="button" data-indice="' + posicion + '" aria-current="' + (posicion === indice) + '">' +
        '<strong>' + esc(fila.cable_marca || fila.cod_cable || 'Fila ' + fila.fila) + (cambios.has(fila.fila) ? ' *' : '') + '</strong>' +
        '<small>' + esc(fila.seccion + ' · ' + fila.de_elemento + ' / ' + fila.para_elemento) + '</small>' +
        '<small>Fila ' + fila.fila + (fila.sugerida ? '' : ' · Preparación existente') + '</small></button>';
    }).join('') || '<p>Sin coincidencias.</p>';
  }

  function numero(campo, etiqueta, valor) {
    return '<label>' + etiqueta + '<input type="number" min="0" max="999999" step="1" data-campo="' + campo + '" value="' + esc(valor) + '"></label>';
  }

  function par(tipo, primero, segundo) {
    var activo = tipo === 'activo';
    return '<div class="me-pair" data-par="' + tipo + '"><label>' + (activo ? 'Nº activo' : 'Código') +
      '<input ' + (activo ? 'type="number" min="1" max="9999" step="1"' : 'type="text" maxlength="100"') +
      ' data-par-clave required value="' + esc(primero) + '"></label><label>Medida (mm)' +
      '<input type="number" min="0" max="999999" step="1" data-par-medida required value="' + esc(segundo) + '"></label>' +
      '<button type="button" data-borrar title="Eliminar ' + (activo ? 'activo' : 'retráctil') + '" aria-label="Eliminar ' + (activo ? 'activo' : 'retráctil') + '">&times;</button></div>';
  }

  function ladoHtml(fila, lado) {
    var inst = fila[lado];
    var modo = inst.m_cortar ? 'cortar' : inst.m_mrs ? 'mrs' : inst.m_mrc ? 'mrc' : inst.m != null ? 'medida' : 'igual';
    var medida = modo === 'mrs' ? inst.m_mrs_medida : modo === 'mrc' ? inst.m_mrc_medida : inst.m;
    var opciones = [['igual', 'Igual que pelado de manguera'], ['medida', 'Pelado de malla'], ['cortar', 'Cortar malla'], ['mrs', 'Hacia atrás sin retráctil'], ['mrc', 'Hacia atrás con retráctil']];
    return '<fieldset class="me-side me-' + lado + '" data-lado="' + lado + '"><legend>Lado ' + (lado === 'de' ? 'De' : 'Para') + '</legend>' +
      '<div class="me-terminal">' + esc(fila[lado + '_elemento'] + ' · ' + (fila[lado + '_terminal'] || 'Sin terminal')) + '</div>' +
      numero('pm', 'Pelado manguera (mm)', inst.pm) +
      '<label>Malla<select data-campo="modo">' + opciones.map(function (opcion) {
        return '<option value="' + opcion[0] + '"' + (modo === opcion[0] ? ' selected' : '') + '>' + opcion[1] + '</option>';
      }).join('') + '</select></label>' + numero('malla', 'Medida malla (mm)', medida) +
      numero('a_todos', 'Todos los activos (mm)', inst.a_todos) +
      '<h3>Activos individuales</h3><div data-pares="activo">' + Object.keys(inst.a_especificos).map(function (activo) {
        return par('activo', activo, inst.a_especificos[activo]);
      }).join('') + '</div><div class="me-add"><button type="button" data-add="activo" title="Añadir activo" aria-label="Añadir activo">+</button><span>Activo</span></div>' +
      '<h3>Retráctiles</h3><div data-pares="retractil">' + fila['retractil_' + lado].map(function (ret) {
        return par('retractil', ret.codigo, ret.medida);
      }).join('') + '</div><div class="me-add"><button type="button" data-add="retractil" title="Añadir retráctil" aria-label="Añadir retráctil">+</button><span>Retráctil</span></div>' +
      '<div class="me-raw" data-preview></div></fieldset>';
  }

  function ajustarMalla(fieldset) {
    var modo = fieldset.querySelector('[data-campo=modo]').value;
    var medida = fieldset.querySelector('[data-campo=malla]');
    medida.disabled = modo === 'igual' || modo === 'cortar';
    medida.required = modo === 'medida';
  }

  function renderActual() {
    if (!datos || !datos.filas.length) return;
    var fila = datos.filas[indice];
    document.getElementById('me-marca').textContent = fila.cable_marca || fila.cod_cable || 'Manguera';
    document.getElementById('me-identity').textContent = fila.seccion + ' · ' + fila.de_elemento + ' / ' + fila.para_elemento + ' · Fila ' + fila.fila;
    document.getElementById('me-counter').textContent = (indice + 1) + ' / ' + datos.filas.length;
    document.getElementById('me-prev').disabled = indice === 0;
    document.getElementById('me-next').disabled = indice === datos.filas.length - 1;
    document.getElementById('me-sides').innerHTML = ladoHtml(fila, 'de') + ladoHtml(fila, 'para');
    document.getElementById('me-fields').innerHTML = Object.keys(fila.campos).map(function (cabecera) {
      return '<dt>' + esc(cabecera) + '</dt><dd>' + esc(fila.campos[cabecera]) + '</dd>';
    }).join('');
    form.querySelectorAll('[data-lado]').forEach(ajustarMalla);
    pendiente = false;
    previsualizar();
  }

  function leerLado(lado) {
    var fieldset = form.querySelector('[data-lado=' + lado + ']');
    function valor(campo) {
      var input = fieldset.querySelector('[data-campo=' + campo + ']');
      return input.value === '' ? null : Number(input.value);
    }
    var modo = fieldset.querySelector('[data-campo=modo]').value;
    var inst = { pm: valor('pm'), m: modo === 'medida' ? valor('malla') : null,
      m_cortar: modo === 'cortar', m_mrs: modo === 'mrs', m_mrc: modo === 'mrc',
      m_mrs_medida: modo === 'mrs' ? valor('malla') : null,
      m_mrc_medida: modo === 'mrc' ? valor('malla') : null,
      a_todos: valor('a_todos'), a_especificos: {}, otros_tokens: datos.filas[indice][lado].otros_tokens || [] };
    fieldset.querySelectorAll('[data-par=activo]').forEach(function (row) {
      var activo = row.querySelector('[data-par-clave]').value;
      if (Object.prototype.hasOwnProperty.call(inst.a_especificos, activo)) throw new Error('El activo ' + activo + ' está repetido en el lado ' + lado + '.');
      inst.a_especificos[activo] = Number(row.querySelector('[data-par-medida]').value);
    });
    var retractiles = Array.from(fieldset.querySelectorAll('[data-par=retractil]')).map(function (row) {
      var codigo = row.querySelector('[data-par-clave]').value.trim();
      if (!codigo || /[/\r\n]/.test(codigo) || /^[=+@-]/.test(codigo)) throw new Error('Código de retráctil no válido en el lado ' + lado + '.');
      return { codigo: codigo, medida: Number(row.querySelector('[data-par-medida]').value) };
    });
    return { inst: inst, retractiles: retractiles };
  }

  function tokens(inst) {
    var resultado = [];
    if (inst.pm != null) resultado.push('PM' + inst.pm);
    if (inst.m_cortar) resultado.push('M_CORTAR');
    else if (inst.m_mrs) resultado.push('MRS' + (inst.m_mrs_medida == null ? '' : inst.m_mrs_medida));
    else if (inst.m_mrc) resultado.push('MRC' + (inst.m_mrc_medida == null ? '' : inst.m_mrc_medida));
    else if (inst.m != null) resultado.push('M' + inst.m);
    if (inst.a_todos != null) resultado.push('A' + inst.a_todos);
    Object.keys(inst.a_especificos).forEach(function (activo) { resultado.push('A' + activo + '_' + inst.a_especificos[activo]); });
    return resultado.concat(inst.otros_tokens).join('/');
  }

  function previsualizar() {
    ['de', 'para'].forEach(function (lado) {
      try {
        var valor = leerLado(lado);
        form.querySelector('[data-lado=' + lado + '] [data-preview]').textContent = tokens(valor.inst);
      } catch (error) { return; }
    });
  }

  function guardarActual() {
    if (!datos || !pendiente) return true;
    if (!form.reportValidity()) return false;
    try {
      var fila = datos.filas[indice];
      var lados = { de: leerLado('de'), para: leerLado('para') };
      ['de', 'para'].forEach(function (lado) {
        var valor = lados[lado];
        fila[lado] = valor.inst;
        fila['retractil_' + lado] = valor.retractiles;
      });
      cambios.set(fila.fila, structuredClone(fila));
      pendiente = false;
      persistir();
      renderLista();
      mensaje('Preparación guardada en el borrador.');
      return true;
    } catch (error) { mensaje(error.message, true); return false; }
  }

  function navegar(posicion) {
    if (ocupado || !guardarActual() || posicion < 0 || posicion >= datos.filas.length) return;
    indice = posicion;
    renderActual();
    renderLista();
  }

  form.addEventListener('submit', function (event) { event.preventDefault(); abrirGuardado(); });
  form.addEventListener('input', function () { pendiente = true; previsualizar(); });
  form.addEventListener('change', function (event) {
    pendiente = true;
    if (event.target.matches('[data-campo=modo]')) ajustarMalla(event.target.closest('[data-lado]'));
    previsualizar();
  });
  form.addEventListener('click', function (event) {
    var add = event.target.closest('[data-add]');
    var borrar = event.target.closest('[data-borrar]');
    if (add) {
      var lista = add.closest('[data-lado]').querySelector('[data-pares=' + add.dataset.add + ']');
      lista.insertAdjacentHTML('beforeend', par(add.dataset.add, '', ''));
      lista.lastElementChild.querySelector('input').focus();
      pendiente = true;
    }
    if (borrar) { borrar.closest('[data-par]').remove(); pendiente = true; previsualizar(); }
  });
  document.getElementById('me-list').addEventListener('click', function (event) {
    var button = event.target.closest('[data-indice]');
    if (button) navegar(Number(button.dataset.indice));
  });
  document.getElementById('me-prev').addEventListener('click', function () { navegar(indice - 1); });
  document.getElementById('me-next').addEventListener('click', function () { navegar(indice + 1); });
  document.getElementById('me-search').addEventListener('input', renderLista);
  document.getElementById('me-reset').addEventListener('click', function () {
    if (!confirm('¿Deshacer los cambios de esta manguera?')) return;
    datos.filas[indice] = structuredClone(originales[indice]);
    cambios.delete(datos.filas[indice].fila);
    persistir(); renderActual(); renderLista();
    mensaje('Preparación original restaurada.');
  });
  document.getElementById('me-file').addEventListener('change', function (event) {
    var file = event.target.files[0];
    if (file) cargar({ file: file });
  });
  document.getElementById('me-load').addEventListener('click', function () {
    var archivo = document.getElementById('me-corte').value;
    if (archivo) cargar({ archivo: archivo });
    else mensaje('Selecciona un corte registrado.', true);
  });
  function abrirGuardado() {
    if (ocupado || !datos || !guardarActual()) return;
    copiaDescargada = false;
    pinForm.hidden = true;
    document.getElementById('me-pin').value = '';
    destino.innerHTML = '<option value="">Seleccionar corte</option>' + cortesDisponibles.map(function (corte) {
      return '<option value="' + esc(corte.archivo) + '">' + esc(corte.codigo + ' · ' + (corte.descripcion || corte.archivo)) + '</option>';
    }).join('');
    destino.value = fuente.archivo || (cortesDisponibles.some(function (corte) { return corte.archivo === datos.nombre; }) ? datos.nombre : '');
    document.getElementById('me-save-summary').textContent = datos.nombre + ' · ' + cambios.size + ' mangueras modificadas.';
    mensajeGuardado(destino.value ? 'Se actualizará el mismo archivo del corte y se conservará una copia anterior.' : 'Solo se puede aplicar sobre un corte existente con el mismo Excel de origen.');
    document.getElementById('me-save-apply').disabled = !destino.value;
    dialogo.showModal();
  }

  function descargarBlob(blob) {
    var url = URL.createObjectURL(blob);
    var enlace = document.createElement('a');
    enlace.href = url;
    enlace.download = datos.nombre.replace(/\.(xlsx|xlsm)$/i, '_preparacion.$1');
    document.body.appendChild(enlace); enlace.click(); enlace.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
  }

  async function obtenerCopia() {
    var body = cuerpo();
    body.append('cambios', JSON.stringify(Array.from(cambios.values())));
    body.append('revision', datos.revision);
    var respuesta = await fetch('/api/mangueras/editor/descargar', { method: 'POST', body: body });
    if (respuesta.redirected) throw new Error('La sesión ha caducado. Vuelve a entrar en mangueras.');
    if (!respuesta.ok) { var error = await respuesta.json(); throw new Error(error.error || error.message || 'No se pudo generar el Excel.'); }
    return respuesta.blob();
  }

  async function guardarExcel(aplicar) {
    if (ocupado || !datos || (aplicar && !destino.value)) return;
    bloquear(true);
    mensajeGuardado('Guardando Excel...');
    try {
      if (!copiaDescargada) {
        descargarBlob(await obtenerCopia());
        copiaDescargada = true;
      }
      if (!aplicar) {
        dialogo.close();
        mensaje('Excel descargado. Los cambios no se han aplicado al corte.');
        return;
      }
      var body = new FormData();
      body.append('destino', destino.value);
      body.append('revision', datos.revision);
      body.append('cambios', JSON.stringify(Array.from(cambios.values())));
      var respuesta = await fetch('/api/mangueras/editor/aplicar', { method: 'POST', body: body });
      if (respuesta.redirected) throw new Error('La sesión ha caducado. Vuelve a entrar en mangueras.');
      var resultado = await respuesta.json();
      if (respuesta.status === 401) {
        pinForm.hidden = false;
        mensajeGuardado('Excel descargado. ' + (resultado.error || resultado.message) + '.', true);
        return;
      }
      if (!respuesta.ok || !resultado.success) throw new Error(resultado.error || resultado.message || 'No se pudo aplicar la preparación.');
      try { localStorage.removeItem(claveBorrador()); } catch (error) { mensaje(error.message, true); }
      datos = resultado.datos;
      fuente = { archivo: resultado.archivo };
      originales = structuredClone(datos.filas);
      cambios = new Map();
      pendiente = false;
      indice = Math.min(indice, Math.max(0, datos.filas.length - 1));
      document.getElementById('me-file').value = '';
      document.getElementById('me-corte').value = resultado.archivo;
      document.getElementById('me-name').textContent = datos.nombre + ' / ' + datos.hoja;
      document.getElementById('me-workspace').hidden = !datos.filas.length;
      persistir(); renderLista(); renderActual();
      dialogo.close();
      mensaje('Excel descargado y preparación aplicada a ' + resultado.archivo + '.');
    } catch (error) {
      mensajeGuardado((copiaDescargada ? 'La copia está descargada, pero no se ha aplicado. ' : '') + error.message, true);
    }
    finally { bloquear(false); }
  }

  download.addEventListener('click', abrirGuardado);
  document.getElementById('me-save-download').addEventListener('click', function () { guardarExcel(false); });
  document.getElementById('me-save-apply').addEventListener('click', function () { guardarExcel(true); });
  document.getElementById('me-save-cancel').addEventListener('click', function () { if (!ocupado) dialogo.close(); });
  destino.addEventListener('change', function () {
    document.getElementById('me-save-apply').disabled = !destino.value;
    pinForm.hidden = true;
    document.getElementById('me-pin').value = '';
  });
  dialogo.addEventListener('cancel', function (event) { if (ocupado) event.preventDefault(); });
  dialogo.addEventListener('close', function () { document.getElementById('me-pin').value = ''; });
  pinForm.addEventListener('submit', async function (event) {
    event.preventDefault();
    if (ocupado) return;
    var body = new FormData();
    body.append('pin', document.getElementById('me-pin').value);
    body.append('next', '/mangueras/editor');
    document.getElementById('me-pin').value = '';
    bloquear(true);
    mensajeGuardado('Validando acceso de administración...');
    var validado = false;
    try {
      var respuesta = await fetch('/admin/pin', { method: 'POST', body: body });
      validado = respuesta.ok && respuesta.redirected && new URL(respuesta.url).pathname === '/mangueras/editor';
      if (!validado) {
        var pagina = new DOMParser().parseFromString(await respuesta.text(), 'text/html');
        var errorPin = pagina.querySelector('.pin-error');
        throw new Error(errorPin ? errorPin.textContent.trim() : 'No se pudo validar el PIN de administración.');
      }
    } catch (error) { mensajeGuardado(error.message, true); }
    finally { bloquear(false); }
    if (validado) await guardarExcel(true);
  });
  window.addEventListener('beforeunload', function (event) {
    if (pendiente || cambios.size || ocupado) { event.preventDefault(); event.returnValue = ''; }
  });
  fetch('/api/codigos_cortes/listar').then(function (respuesta) { return respuesta.json(); }).then(function (resultado) {
    if (!resultado.success) throw new Error('No se pudo cargar la lista de cortes.');
    cortesDisponibles = (resultado.codigos || []).filter(function (corte) { return corte.archivo; });
    document.getElementById('me-corte').innerHTML += cortesDisponibles.map(function (corte) {
      return '<option value="' + esc(corte.archivo) + '">' + esc(corte.codigo + ' · ' + (corte.descripcion || corte.proyecto || corte.archivo)) + '</option>';
    }).join('');
  }).catch(function () { mensaje('No se pudieron listar los cortes. Puedes abrir un Excel local.', true); });
})();