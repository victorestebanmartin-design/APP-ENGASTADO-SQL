// v3-embalaje.js — Embalaje de las órdenes terminadas (lógica en app/embalaje.py).
//
// Botón EMBALAJE de engastado: solo se enciende si hay alguna orden con todas
// sus máquinas acabadas. Flujo: tarjeta del operario → bono → orden →
//   - primera vez del código de corte: nº de cajas y qué paquetes van en cada una;
//   - siguientes veces: el reparto guardado, ya guiado.
// Los carteles se imprimen antes de empezar, para dejar cada caja con el suyo.
//
// Las reglas las pone el servidor (supervisor para pendientes o para rehacer
// un reparto); esta pantalla solo las explica y pide la tarjeta cuando toca.

const EMB_POLL_MS = 1000;
const EMB_REFRESCO_BOTON_MS = 60000;
const EMB_COLORES = ['#2563eb', '#16a34a', '#d97706', '#9333ea', '#dc2626',
                     '#0891b2', '#db2777', '#65a30d', '#4f46e5', '#ea580c'];

let _emb = null;   // contexto de la pantalla abierta (null = cerrada)

function _escEmb(valor) {
    return String(valor ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function _colorCaja(n) {
    return EMB_COLORES[(Number(n) - 1) % EMB_COLORES.length];
}

function _plural(n, uno, varios) {
    return `${n} ${n === 1 ? uno : varios}`;
}

function _fechaEmb(iso) {
    if (!iso) return '';
    const d = new Date(String(iso).replace(' ', 'T'));
    return isNaN(d) ? iso : d.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

async function _embApi(url, opciones) {
    let r;
    try {
        r = await fetch(url, opciones);
    } catch {
        return { success: false, motivo: 'Sin conexión con el servidor', consejo: 'Vuelve a intentarlo', _status: 0 };
    }
    let d;
    try { d = await r.json(); } catch { d = { success: false, motivo: 'Respuesta no válida del servidor' }; }
    d._status = r.status;
    return d;
}

function _embPost(url, cuerpo) {
    return _embApi(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cuerpo || {}),
    });
}

function _puestoEmb() {
    if (window.RFID_PUESTO_ID) return window.RFID_PUESTO_ID;
    if (typeof puestoSeleccionado !== 'undefined' && puestoSeleccionado) return puestoSeleccionado.id || '';
    return '';
}

// ==================== botón ====================

async function actualizarBotonEmbalaje() {
    const d = await _embApi('/api/embalaje/disponible');
    document.querySelectorAll('.btn-embalaje').forEach(b => {
        b.disabled = !d.disponible;
        b.title = d.disponible ? 'Embalar órdenes terminadas' : (d.motivo || 'No hay órdenes terminadas');
    });
}

document.addEventListener('DOMContentLoaded', () => {
    actualizarBotonEmbalaje();
    setInterval(() => { if (!_emb) actualizarBotonEmbalaje(); }, EMB_REFRESCO_BOTON_MS);
});

// ==================== marco ====================

function abrirEmbalaje() {
    if (_emb) return;
    const overlay = document.createElement('div');
    overlay.className = 'modal-operario-overlay';
    overlay.id = 'modal-embalaje';
    overlay.innerHTML = '<div class="emb-card"></div>';
    document.body.appendChild(overlay);
    _emb = { overlay, card: overlay.querySelector('.emb-card'), temporizador: null };
    _embIdentificacion();
}

function cerrarEmbalaje() {
    if (!_emb) return;
    _embParar();
    _emb.overlay.remove();
    _emb = null;
    actualizarBotonEmbalaje();
}

function _embParar() {
    if (_emb && _emb.temporizador) {
        clearInterval(_emb.temporizador);
        _emb.temporizador = null;
    }
}

/** Pinta cabecera, cuerpo y pie. botones: [{id, texto, clase, accion}] */
function _embMarco(icono, titulo, subtitulo, cuerpo, botones, ancho) {
    _embParar();
    const card = _emb.card;
    card.classList.toggle('ancha', !!ancho);
    card.innerHTML = `
        <div class="emb-header">
            <div class="emb-icon">${icono}</div>
            <h2>${titulo}</h2>
            ${subtitulo ? `<p>${subtitulo}</p>` : ''}
            ${_emb.operario ? `<span class="emb-quien">👤 ${_escEmb(_emb.operario)}</span>` : ''}
        </div>
        <div class="emb-body"><div class="ensayo-aviso" id="emb-aviso" style="display:none"></div>${cuerpo}</div>
        <div class="emb-footer">${(botones || []).map(b =>
            `<button type="button" id="${b.id}" class="${b.clase || 'btn-volver-modal'}" ${b.disabled ? 'disabled' : ''}>${b.texto}</button>`
        ).join('')}</div>`;
    (botones || []).forEach(b => {
        const el = card.querySelector('#' + b.id);
        if (el && b.accion) el.onclick = b.accion;
    });
    card.scrollTop = 0;
    return card;
}

function _embAviso(motivo, consejo, tipo) {
    const aviso = _emb && _emb.card.querySelector('#emb-aviso');
    if (!aviso) return;
    aviso.className = tipo === 'ok' ? 'emb-ok' : 'ensayo-aviso';
    aviso.innerHTML = _escEmb(motivo) + (consejo ? `<br><small>${_escEmb(consejo)}</small>` : '');
    aviso.style.display = 'block';
    _emb.card.scrollTop = 0;
}

function _embAvisoDe(d) {
    _embAviso(d.motivo || d.message || 'No se ha podido hacer', d.consejo);
}

const _BTN_CERRAR = () => ({ id: 'emb-cerrar', texto: '✕ Cerrar', accion: cerrarEmbalaje });

// ==================== 1. quién embala ====================

function _embIdentificacion() {
    _embMarco('📦', 'Embalaje', 'Identifícate para empezar', `
        <div id="emb-zona-tarjeta" class="ensayo-espera">💳 Pasa tu tarjeta por el lector del puesto…
            <small id="emb-tarjeta-msg"></small></div>
        <button type="button" class="ensayo-btn-link" id="emb-manual">o elige tu nombre en la lista</button>`,
        [_BTN_CERRAR()]);
    _emb.card.querySelector('#emb-manual').onclick = () => _embListaOperarios();
    _embTarjetaOperario();
}

async function _embTarjetaOperario() {
    const d = await _embPost('/api/embalaje/operario/tarjeta', { puesto_id: _puestoEmb() });
    if (!_emb) return;
    if (!d.success) {
        if (d.sin_lector) return _embListaOperarios(d.motivo);
        _embAvisoDe(d);
        return;
    }
    const limite = Date.now() + (d.segundos || 120) * 1000;
    _emb.temporizador = setInterval(async () => {
        const e = await _embApi(`/api/embalaje/operario/tarjeta/${encodeURIComponent(d.token)}`);
        if (!_emb) return;
        const msg = _emb.card.querySelector('#emb-tarjeta-msg');
        if (e.estado === 'asignada') {
            _embParar();
            _emb.operario = e.operario;
            _emb.operarioVia = 'tarjeta';
            _embBonos();
        } else if ((e.estado && e.estado !== 'armada') || Date.now() > limite) {
            _embParar();
            const zona = _emb.card.querySelector('#emb-zona-tarjeta');
            if (zona) zona.outerHTML = `<button type="button" class="ensayo-btn-sup" id="emb-otra-vez">💳 Volver a pasar la tarjeta</button>`;
            const otra = _emb.card.querySelector('#emb-otra-vez');
            if (otra) otra.onclick = () => _embIdentificacion();
            _embAviso('Se acabó el tiempo para pasar la tarjeta', 'Pulsa «Volver a pasar la tarjeta» o elige tu nombre');
        } else if (msg && e.mensaje) {
            msg.textContent = e.mensaje;   // «Tarjeta no registrada», etc.
        }
    }, EMB_POLL_MS);
}

async function _embListaOperarios(motivo) {
    _embParar();
    const d = await _embApi('/api/operarios');
    if (!_emb) return;
    const ops = (d.operarios || []).filter(o => o.activo);
    _embMarco('📦', 'Embalaje', motivo ? _escEmb(motivo) : '¿Quién embala?', `
        <label class="ensayo-label">Operario
            <select id="emb-operario"><option value="">— Elige tu nombre —</option>${ops.map(o =>
                `<option value="${_escEmb(o.nombre)}" ${o.nombre === (typeof operarioActual !== 'undefined' ? operarioActual : '') ? 'selected' : ''}>${_escEmb(o.nombre)}</option>`
            ).join('')}</select></label>`,
        [_BTN_CERRAR(),
         { id: 'emb-entrar', texto: 'Entrar', clase: 'ensayo-btn-ok', accion: () => {
             const nombre = _emb.card.querySelector('#emb-operario').value;
             if (!nombre) return _embAviso('Elige tu nombre en la lista');
             _emb.operario = nombre;
             _emb.operarioVia = 'lista';
             _embBonos();
         } }]);
}

// ==================== 2. bono ====================

async function _embBonos() {
    _embMarco('📦', 'Embalaje', 'Elige el bono', `
        <div class="emb-buscar">
            <input type="text" id="emb-bono-codigo" placeholder="Escribe o escanea el código del bono" autocomplete="off">
            <button type="button" class="ensayo-btn-ok" id="emb-bono-ir">Abrir</button>
        </div>
        <div id="emb-bonos" class="emb-lista"><p class="emb-cargando">Cargando bonos…</p></div>`,
        [_BTN_CERRAR()]);
    const input = _emb.card.querySelector('#emb-bono-codigo');
    const ir = () => { if (input.value.trim()) _embOrdenes(input.value.trim()); };
    _emb.card.querySelector('#emb-bono-ir').onclick = ir;
    input.onkeydown = e => { if (e.key === 'Enter') ir(); };
    input.focus();

    const d = await _embApi('/api/embalaje/bonos');
    if (!_emb) return;
    const zona = _emb.card.querySelector('#emb-bonos');
    if (!zona) return;
    if (!d.success) { zona.innerHTML = ''; return _embAvisoDe(d); }
    if (!d.bonos.length) {
        zona.innerHTML = '<p class="emb-cargando">No hay bonos con órdenes terminadas.</p>';
        return;
    }
    zona.innerHTML = d.bonos.map(b => `
        <div class="emb-item" data-bono="${_escEmb(b.nombre)}">
            <div>
                <div class="emb-item-titulo">${_escEmb(b.nombre)} ${b.estado !== 'activo' ? '<span class="emb-chip gris">cerrado</span>' : ''}</div>
                <div class="emb-item-sub">${b.listas} de ${_plural(b.total, 'orden lista', 'órdenes listas')} · ${_plural(b.embaladas, 'embalada', 'embaladas')}</div>
            </div>
            <span class="emb-flecha">▶</span>
        </div>`).join('');
    zona.querySelectorAll('[data-bono]').forEach(el => { el.onclick = () => _embOrdenes(el.dataset.bono); });
}

// ==================== 3. órdenes del bono ====================

async function _embOrdenes(nombreBono) {
    _emb.bono = nombreBono;
    _embMarco('📦', `Bono ${_escEmb(nombreBono)}`, 'Elige la orden que vas a embalar',
        '<div id="emb-ordenes" class="emb-lista"><p class="emb-cargando">Cargando órdenes…</p></div>',
        [{ id: 'emb-volver', texto: '← Cambiar bono', accion: _embBonos }, _BTN_CERRAR()], true);
    const d = await _embApi(`/api/embalaje/bono/${encodeURIComponent(nombreBono)}`);
    if (!_emb) return;
    const zona = _emb.card.querySelector('#emb-ordenes');
    if (!zona) return;
    if (!d.success) { zona.innerHTML = ''; return _embAvisoDe(d); }

    zona.innerHTML = d.ordenes.map(o => {
        const clase = o.embalada ? 'embalada' : o.estado;
        let estado;
        if (o.estado === 'incompleta') estado = `<span class="emb-chip gris">${_escEmb(o.motivo)}</span>`;
        else if (o.estado === 'pendientes') estado = `<span class="emb-chip naranja">⚠️ ${_escEmb(o.motivo)} · necesita supervisor</span>`;
        else estado = '<span class="emb-chip verde">Lista para embalar</span>';
        const embalada = o.embalada
            ? `<span class="emb-chip verde">✅ Embalada ${_escEmb(_fechaEmb(o.embalada.fecha))} · ${_escEmb(o.embalada.operario || '')} · ${_plural(o.embalada.num_cajas, 'caja', 'cajas')}</span>`
            : '';
        const reparto = o.estado === 'incompleta' ? '' : (o.reparto
            ? `<span class="emb-chip azul">Reparto guardado: ${_plural(o.reparto.num_cajas, 'caja', 'cajas')}</span>`
            : '<span class="emb-chip azul">Primera vez: hay que repartir</span>');
        return `
            <div class="emb-orden ${clase}" ${o.estado !== 'incompleta' ? `data-orden="${_escEmb(o.id)}"` : ''}>
                <div class="emb-orden-carro">Carro ${_escEmb(o.carro)}</div>
                <div class="emb-orden-datos">
                    <div class="emb-orden-corte">${_escEmb(o.codigo_corte)}</div>
                    <div class="emb-item-sub">Orden <strong>${_escEmb(o.numero)}</strong> · ${_escEmb(o.descripcion)} · x${_escEmb(o.cantidad)}</div>
                    <div class="emb-chips">${o.embalada ? embalada : estado} ${reparto}</div>
                </div>
            </div>`;
    }).join('') || '<p class="emb-cargando">Este bono no tiene órdenes.</p>';
    zona.querySelectorAll('[data-orden]').forEach(el => { el.onclick = () => _embAbrirOrden(el.dataset.orden); });
}

// ==================== 4. una orden ====================

async function _embAbrirOrden(ordenId, opciones) {
    const opc = opciones || {};
    _embParar();
    const d = await _embApi(`/api/embalaje/orden/${encodeURIComponent(ordenId)}`);
    if (!_emb) return;
    if (!d.success) return _embAvisoDe(d);
    _emb.datos = d;
    _emb.ordenId = ordenId;

    const o = d.orden;
    if (o.estado === 'pendientes' && !o.embalada && !d.autorizado_por) {
        const ok = await _embPedirSupervisor(
            'Esta orden tiene paquetes pendientes',
            `${o.motivo}. Para embalarla así, tiene que autorizarlo un supervisor.`);
        if (!ok) return _embOrdenes(_emb.bono);
        return _embAbrirOrden(ordenId, opc);
    }
    if (!d.reparto) return _embNumCajas('nuevo');
    if (d.cantidad_distinta && !opc.cantidadAceptada) return _embAvisoCantidad();
    if (d.paquetes_nuevos.length) return _embEditor(d.reparto.num_cajas, { ...d.reparto.asignaciones }, 'completar');
    return _embGuiado();
}

function _embCabeceraOrden() {
    const o = _emb.datos.orden;
    return `Orden <strong>${_escEmb(o.numero)}</strong> · ${_escEmb(o.codigo_corte)} · ${_escEmb(o.descripcion)} · x${_escEmb(o.cantidad)}`;
}

const _BTN_ORDENES = () => ({ id: 'emb-ordenes-volver', texto: '← Órdenes', accion: () => _embOrdenes(_emb.bono) });

function _embAvisoCantidad() {
    const d = _emb.datos;
    _embMarco('⚠️', 'La cantidad no coincide', _embCabeceraOrden(), `
        <div class="ensayo-motivo">El reparto guardado para ${_escEmb(d.orden.codigo_corte)} se hizo para
            <strong>${_escEmb(d.reparto.cantidad_ref)}</strong> y esta orden es de <strong>${_escEmb(d.orden.cantidad)}</strong>.</div>
        <p class="emb-texto">Reparto guardado: ${_plural(d.reparto.num_cajas, 'caja', 'cajas')}. ¿Lo usas igual o haces uno nuevo?</p>
        <div class="emb-dos">
            <button type="button" class="ensayo-btn-ok" id="emb-usar">Usar el reparto guardado</button>
            <button type="button" class="ensayo-btn-sup" id="emb-nuevo">Hacer uno nuevo (supervisor)</button>
        </div>`, [_BTN_ORDENES()]);
    _emb.card.querySelector('#emb-usar').onclick = () => _embAbrirOrden(_emb.ordenId, { cantidadAceptada: true });
    _emb.card.querySelector('#emb-nuevo').onclick = () => _embRehacer();
}

async function _embRehacer() {
    // Si un supervisor ya ha autorizado esta orden hace poco, no se le vuelve
    // a pedir; si su autorización ha caducado, el servidor lo dirá al guardar.
    const ok = _emb.datos.autorizado_por || await _embPedirSupervisor('Rehacer el reparto',
        'Cambiar un reparto guardado necesita un supervisor: el nuevo vale para todas las órdenes de esta referencia.');
    if (!ok) return _embAbrirOrden(_emb.ordenId, { cantidadAceptada: true });
    _embNumCajas('rehacer');
}

// ---------- nº de cajas ----------

function _embNumCajas(modo) {
    const actual = _emb.datos.reparto ? _emb.datos.reparto.num_cajas : null;
    _embMarco('📦', '¿Cuántas cajas?', _embCabeceraOrden(), `
        <p class="emb-texto">${modo === 'rehacer' ? 'Reparto nuevo: elige' : 'Primera vez que se embala esta referencia. Elige'} en cuántas cajas va
            (${_plural(_emb.datos.paquetes.length, 'paquete', 'paquetes')}).</p>
        <div class="emb-num-cajas">${[1, 2, 3, 4, 5, 6].map(n =>
            `<button type="button" class="emb-num ${n === actual ? 'activa' : ''}" data-n="${n}">${n}</button>`).join('')}
            <input type="number" id="emb-num-otro" min="1" max="50" placeholder="Otro" inputmode="numeric">
        </div>`,
        [_BTN_ORDENES(), { id: 'emb-num-ok', texto: 'Seguir →', clase: 'ensayo-btn-ok', accion: () => {
            const n = parseInt(_emb.card.querySelector('#emb-num-otro').value, 10);
            if (!(n >= 1 && n <= 50)) return _embAviso('Escribe un número de cajas entre 1 y 50');
            _embElegirCajas(n, modo);
        } }]);
    _emb.card.querySelectorAll('.emb-num').forEach(b => { b.onclick = () => _embElegirCajas(Number(b.dataset.n), modo); });
}

function _embElegirCajas(n, modo) {
    const paquetes = _emb.datos.paquetes;
    if (n === 1) {
        // Una caja: todo va en ella, no hay nada que repartir.
        const todo = Object.fromEntries(paquetes.map(p => [p.clave, 1]));
        return _embGuardarReparto(1, todo);
    }
    // Al rehacer se parte de lo guardado (si cabe en las cajas nuevas).
    const previo = modo === 'rehacer' && _emb.datos.reparto ? _emb.datos.reparto.asignaciones : {};
    const asign = {};
    Object.entries(previo).forEach(([k, v]) => { if (v <= n) asign[k] = v; });
    _embEditor(n, asign, modo);
}

// ---------- reparto: elegir caja y tocar paquetes ----------

function _embEditor(numCajas, asignaciones, modo) {
    _emb.editor = { num: numCajas, asign: asignaciones, activa: 1, modo };
    _embPintarEditor();
}

function _embTarjetaPaquete(p, caja, extra, conBotonObs) {
    const color = typeof getCodCableColor === 'function'
        ? getCodCableColor(p.es_serie ? 'GRUPO_SERIE' : p.cod_cable) : { bg: '#6b7280', text: '#fff' };
    const contenido = p.es_serie
        ? `${_plural(p.contenido.length, 'paquete', 'paquetes')}: ${p.contenido.map(c => _escEmb(c.cod_cable)).join(', ')}`
        : _escEmb(p.descripcion);
    return `
        <div class="emb-paq ${extra || ''} ${p.observacion ? 'con-obs' : ''}" data-clave="${_escEmb(p.clave)}"
             style="${caja ? `--caja:${_colorCaja(caja)}` : ''}">
            ${caja ? `<span class="emb-paq-caja">${caja}</span>` : ''}
            ${conBotonObs ? `<button type="button" class="emb-obs-btn" data-obs="${_escEmb(p.clave)}"
                title="Observación: lo que hay que hacerle antes de meterlo en la caja">📝</button>` : ''}
            <div class="emb-paq-num">${p.observacion ? '<span class="emb-asterisco">*</span>' : ''}${_escEmb(p.etiqueta)}</div>
            <div class="emb-paq-cable" style="background:${color.bg};color:${color.text}">${p.es_serie ? 'SERIE ' + _escEmb(p.serie) : _escEmb(p.cod_cable)}</div>
            <div class="emb-paq-elem">${_escEmb(p.elemento)}</div>
            <div class="emb-paq-desc">${contenido}</div>
            ${p.observacion ? `<div class="emb-paq-obs">* ${_escEmb(p.observacion)}</div>` : ''}
        </div>`;
}

// ---------- observaciones: lo que hay que hacerle antes de meterlo en la caja ----------

/** Engancha los botones 📝 de las tarjetas pintadas; repintar() vuelve a la vista. */
function _embBotonesObs(repintar) {
    _emb.card.querySelectorAll('.emb-obs-btn').forEach(b => {
        b.onclick = ev => { ev.stopPropagation(); _embEditarObs(b.dataset.obs, repintar); };
    });
}

/** Ventanita para escribir un texto corto encima de la pantalla.
 *  opc: {titulo, explicacion (html), valor, max, filas, placeholder, repintar,
 *        enviar(texto) → Promise<respuesta>, alGuardar(respuesta)} */
function _embPanelTexto(opc) {
    const panel = document.createElement('div');
    panel.className = 'emb-obs-panel';
    const campo = opc.filas > 1
        ? `<textarea id="emb-panel-texto" maxlength="${opc.max}" rows="${opc.filas}" placeholder="${_escEmb(opc.placeholder)}">${_escEmb(opc.valor)}</textarea>`
        : `<input type="text" id="emb-panel-texto" maxlength="${opc.max}" placeholder="${_escEmb(opc.placeholder)}" value="${_escEmb(opc.valor)}">`;
    panel.innerHTML = `
        <div class="emb-obs-caja ${opc.clase || ''}">
            <h3>${opc.titulo}</h3>
            <p class="emb-texto">${opc.explicacion}</p>
            ${campo}
            <div class="ensayo-aviso" id="emb-panel-aviso" style="display:none"></div>
            <div class="emb-footer">
                <button type="button" class="btn-volver-modal" id="emb-panel-cancelar">Cancelar</button>
                ${opc.valor ? '<button type="button" class="btn-volver-modal" id="emb-panel-quitar">Quitar</button>' : ''}
                <button type="button" class="ensayo-btn-ok" id="emb-panel-guardar">Guardar</button>
            </div>
        </div>`;
    _emb.overlay.appendChild(panel);
    const campoEl = panel.querySelector('#emb-panel-texto');
    campoEl.focus();
    const cerrar = () => panel.remove();
    const guardar = async texto => {
        panel.querySelectorAll('button').forEach(b => { b.disabled = true; });
        let d = await opc.enviar(texto);
        if (!_emb) return;
        if (d.supervisor_requerido) {
            // La autorización ha caducado mientras se escribía: se pide otra
            // y se guarda lo escrito, sin tener que volver a teclearlo.
            panel.style.display = 'none';
            const ok = await _embPedirSupervisor(opc.titulo.replace(/<[^>]*>/g, ''), d.motivo || '');
            if (!_emb) return;
            opc.repintar();
            if (!ok) return cerrar();
            panel.style.display = '';
            d = await opc.enviar(texto);
            if (!_emb) return;
        }
        if (!d.success) {
            panel.querySelectorAll('button').forEach(b => { b.disabled = false; });
            const aviso = panel.querySelector('#emb-panel-aviso');
            aviso.innerHTML = _escEmb(d.motivo || d.message || 'No se ha podido guardar') +
                (d.consejo ? `<br><small>${_escEmb(d.consejo)}</small>` : '');
            aviso.style.display = 'block';
            return;
        }
        cerrar();
        const scroll = _emb.card.scrollTop;
        opc.alGuardar(d);
        _emb.card.scrollTop = scroll;
    };
    panel.querySelector('#emb-panel-cancelar').onclick = cerrar;
    panel.querySelector('#emb-panel-guardar').onclick = () => guardar(campoEl.value);
    if (opc.filas <= 1) campoEl.onkeydown = e => { if (e.key === 'Enter') guardar(campoEl.value); };
    const quitar = panel.querySelector('#emb-panel-quitar');
    if (quitar) quitar.onclick = () => guardar('');
}

/** Observaciones y nombres de caja los autoriza un supervisor: se pide antes
 *  de escribir (si no hay uno autorizado ya en esta orden). Promise<bool>. */
async function _embSupervisorParaEditar(titulo, explicacion, repintar) {
    if (_emb.datos.autorizado_por) return true;
    const ok = await _embPedirSupervisor(titulo, explicacion);
    if (!_emb) return false;
    repintar();
    return ok;
}

async function _embEditarObs(clave, repintar) {
    const p = _emb.datos.paquetes.find(x => x.clave === clave);
    if (!p) return;
    const ok = await _embSupervisorParaEditar('Observación de un paquete',
        'Poner, cambiar o quitar una observación necesita un supervisor: vale para todas las órdenes de esta referencia.',
        repintar);
    if (!ok) return;
    _embPanelTexto({
        repintar,
        titulo: `* Observación del paquete ${_escEmb(p.etiqueta)}`,
        explicacion: `${_escEmb(p.es_serie ? 'Serie ' + p.serie : p.cod_cable + ' · ' + p.elemento)}<br>
            <small>Lo que hay que hacerle antes de meterlo en la caja. Sale con * en la pantalla y en el cartel,
            en todas las órdenes de ${_escEmb(_emb.datos.orden.codigo_corte)}.</small>`,
        valor: p.observacion || '', max: 200, filas: 3,
        placeholder: 'Ej.: poner capuchón, encintar las puntas…',
        enviar: texto => _embPost(`/api/embalaje/orden/${encodeURIComponent(_emb.ordenId)}/observacion`,
                                  { clave, texto, operario: _emb.operario }),
        alGuardar: d => { p.observacion = d.observacion; repintar(); },
    });
}

// ---------- nombres de las cajas: «CAJA 1 de 3» se queda, el nombre se añade ----------

function _embNombreCaja(n) {
    return ((_emb.datos.nombres_cajas || {})[String(n)]) || '';
}

async function _embRenombrarCaja(n, total, repintar) {
    const ok = await _embSupervisorParaEditar('Nombre de una caja',
        'Poner o cambiar el nombre de una caja necesita un supervisor: vale para todas las órdenes de esta referencia.',
        repintar);
    if (!ok) return;
    _embPanelTexto({
        repintar,
        titulo: `Nombre de la caja ${n} de ${total}`,
        clase: 'nombre-caja',
        explicacion: `<small>Sale en la pantalla y en el cartel junto a «CAJA ${n} de ${total}», en todas las
            órdenes de ${_escEmb(_emb.datos.orden.codigo_corte)}.</small>`,
        valor: _embNombreCaja(n), max: 40, filas: 1,
        placeholder: 'Ej.: Conectores, Lado izquierdo…',
        enviar: nombre => _embPost(`/api/embalaje/orden/${encodeURIComponent(_emb.ordenId)}/caja_nombre`,
                                   { caja: n, nombre, operario: _emb.operario }),
        alGuardar: d => {
            _emb.datos.nombres_cajas = { ...(_emb.datos.nombres_cajas || {}) };
            if (d.nombre) _emb.datos.nombres_cajas[String(n)] = d.nombre;
            else delete _emb.datos.nombres_cajas[String(n)];
            repintar();
        },
    });
}

function _embPintarEditor() {
    const ed = _emb.editor;
    const paquetes = _emb.datos.paquetes;
    const nuevos = new Set(_emb.datos.paquetes_nuevos || []);
    const cuenta = n => paquetes.filter(p => ed.asign[p.clave] === n).length;
    const sinCaja = paquetes.filter(p => !ed.asign[p.clave]).length;

    let banner = '<p class="emb-texto">Elige una caja arriba y toca los paquetes que van en ella. Tocar otra vez lo quita. ' +
                 'Con 📝 le pones una observación (algo que hacerle antes de meterlo).</p>';
    if (ed.modo === 'completar') {
        banner = `<div class="ensayo-motivo">El Excel trae ${_plural(nuevos.size, 'paquete nuevo', 'paquetes nuevos')} (marcados).
                  Ponlos en su caja; los demás siguen donde estaban.</div>`;
    } else if (ed.modo === 'rehacer') {
        banner = `<div class="ensayo-motivo">Rehaciendo el reparto${_emb.datos.autorizado_por ? ` · autorizado por ${_escEmb(_emb.datos.autorizado_por)}` : ''}.
                  Toca los paquetes para cambiarlos de caja.</div>`;
    }

    const tabs = Array.from({ length: ed.num }, (_, i) => i + 1).map(n => `
        <button type="button" class="emb-tab ${n === ed.activa ? 'activa' : ''}" data-caja="${n}" style="--caja:${_colorCaja(n)}">
            Caja ${n}${_embNombreCaja(n) ? ` · ${_escEmb(_embNombreCaja(n))}` : ''}<small>${cuenta(n)}</small></button>`).join('');

    _embMarco('📦', 'Reparto en cajas', _embCabeceraOrden(), `
        ${banner}
        <div class="emb-tabs">${tabs}<span class="emb-sin-caja ${sinCaja ? '' : 'cero'}">Sin caja: ${sinCaja}</span></div>
        <button type="button" class="ensayo-btn-link" id="emb-renombrar">✏️ Poner nombre a la caja ${ed.activa}</button>
        ${sinCaja ? `<button type="button" class="ensayo-btn-link" id="emb-resto">Poner los ${sinCaja} que faltan en la caja ${ed.activa}</button>` : ''}
        <div class="emb-paquetes">${paquetes.map(p =>
            _embTarjetaPaquete(p, ed.asign[p.clave], `tocable ${nuevos.has(p.clave) ? 'nuevo' : ''}`, true)).join('')}</div>`,
        [_BTN_ORDENES(),
         { id: 'emb-cambiar-num', texto: 'Cambiar nº de cajas', accion: () => _embNumCajas(ed.modo === 'nuevo' ? 'nuevo' : 'rehacer') },
         { id: 'emb-guardar', texto: sinCaja ? `Faltan ${sinCaja} sin caja` : '💾 Guardar reparto', clase: 'ensayo-btn-ok',
           disabled: sinCaja > 0, accion: () => _embGuardarReparto(ed.num, ed.asign) }], true);

    // En «completar» no se cambia el número de cajas: eso sería rehacerlo.
    if (ed.modo === 'completar') _emb.card.querySelector('#emb-cambiar-num').remove();

    _emb.card.querySelectorAll('.emb-tab').forEach(b => {
        b.onclick = () => { ed.activa = Number(b.dataset.caja); _embPintarEditor(); };
    });
    const resto = _emb.card.querySelector('#emb-resto');
    if (resto) resto.onclick = () => {
        paquetes.forEach(p => { if (!ed.asign[p.clave]) ed.asign[p.clave] = ed.activa; });
        _embPintarEditor();
    };
    _embBotonesObs(_embPintarEditor);
    _emb.card.querySelector('#emb-renombrar').onclick = () => _embRenombrarCaja(ed.activa, ed.num, _embPintarEditor);
    _emb.card.querySelectorAll('.emb-paq.tocable').forEach(el => {
        el.onclick = () => {
            const clave = el.dataset.clave;
            if (ed.asign[clave] === ed.activa) delete ed.asign[clave];
            else ed.asign[clave] = ed.activa;
            const scroll = _emb.card.scrollTop;
            _embPintarEditor();
            _emb.card.scrollTop = scroll;
        };
    });
}

async function _embGuardarReparto(numCajas, asignaciones) {
    const boton = _emb.card.querySelector('#emb-guardar');
    if (boton) boton.disabled = true;
    const d = await _embPost(`/api/embalaje/orden/${encodeURIComponent(_emb.ordenId)}/reparto`, {
        num_cajas: numCajas, asignaciones, operario: _emb.operario,
    });
    if (!_emb) return;
    if (d.success) return _embAbrirOrden(_emb.ordenId, { cantidadAceptada: true });
    if (d.supervisor_requerido) {
        const ok = await _embPedirSupervisor('Has cambiado un reparto guardado', d.consejo || d.motivo);
        if (ok) return _embGuardarReparto(numCajas, asignaciones);
        if (_emb.editor) return _embPintarEditor();
        return _embAbrirOrden(_emb.ordenId, { cantidadAceptada: true });
    }
    if (boton) boton.disabled = false;
    _embAvisoDe(d);
}

// ---------- guiado: carteles primero, luego qué va en cada caja ----------

function _embGuiado(mensaje) {
    const d = _emb.datos;
    const o = d.orden;
    const asign = d.reparto.asignaciones;
    const num = d.reparto.num_cajas;
    const cajas = Array.from({ length: num }, (_, i) => d.paquetes.filter(p => asign[p.clave] === i + 1));
    const impresos = o.embalada;
    const conObs = d.paquetes.filter(p => p.observacion && asign[p.clave]);

    _embMarco('📦', `Embalar en ${_plural(num, 'caja', 'cajas')}`, _embCabeceraOrden(), `
        <div class="emb-paso">
            <div class="emb-paso-num">1</div>
            <div class="emb-paso-texto">
                <strong>Imprime los carteles y pega cada uno en su caja</strong>
                ${impresos ? `<small>Ya impresos el ${_escEmb(_fechaEmb(impresos.fecha))} por ${_escEmb(impresos.operario || '—')}</small>` : ''}
            </div>
            <button type="button" class="ensayo-btn-ok" id="emb-imprimir">🖨️ ${impresos ? 'Reimprimir' : 'Imprimir'} ${_plural(num, 'cartel', 'carteles')}</button>
        </div>
        <button type="button" class="ensayo-btn-link" id="emb-ver">Ver los carteles en el navegador</button>
        <div class="emb-paso">
            <div class="emb-paso-num">2</div>
            <div class="emb-paso-texto"><strong>Mete en cada caja sus paquetes</strong>
                <small>Con 📝 le pones o cambias la observación a un paquete</small></div>
        </div>
        ${conObs.length ? `
            <div class="emb-obs-lista">
                <h3>* Antes de meterlos en la caja</h3>
                ${conObs.map(p => `<div><b>* ${_escEmb(p.etiqueta)}</b> <span class="emb-obs-pq">caja ${asign[p.clave]} ·
                    ${_escEmb(p.es_serie ? 'Serie ' + p.serie : p.cod_cable + ' ' + p.elemento)}</span> ${_escEmb(p.observacion)}</div>`).join('')}
            </div>` : ''}
        ${cajas.map((lista, i) => `
            <div class="emb-caja" style="--caja:${_colorCaja(i + 1)}">
                <div class="emb-caja-cab">
                    <span>CAJA ${i + 1} de ${num}</span>
                    ${_embNombreCaja(i + 1) ? `<strong class="emb-caja-nombre">${_escEmb(_embNombreCaja(i + 1))}</strong>` : ''}
                    <button type="button" class="emb-renombrar" data-caja="${i + 1}">✏️ ${_embNombreCaja(i + 1) ? 'Cambiar nombre' : 'Poner nombre'}</button>
                    <small>${_plural(lista.length, 'paquete', 'paquetes')}</small>
                    <button type="button" class="emb-reimprimir" data-caja="${i + 1}">🖨️ Solo este cartel</button>
                </div>
                <div class="emb-paquetes">${lista.map(p => _embTarjetaPaquete(p, null, '', true)).join('')}</div>
            </div>`).join('')}`,
        [_BTN_ORDENES(),
         { id: 'emb-rehacer', texto: '✏️ Rehacer reparto', accion: _embRehacer },
         { id: 'emb-terminar', texto: '✅ Terminar', clase: 'ensayo-btn-ok', accion: () => _embOrdenes(_emb.bono) }], true);

    _emb.card.querySelector('#emb-imprimir').onclick = () => _embImprimir(null);
    _emb.card.querySelector('#emb-ver').onclick = () => window.open(
        `/api/embalaje/orden/${encodeURIComponent(_emb.ordenId)}/carteles.html`, '_blank');
    _emb.card.querySelectorAll('.emb-reimprimir').forEach(b => {
        b.onclick = () => _embImprimir([Number(b.dataset.caja)]);
    });
    _embBotonesObs(() => _embGuiado());
    _emb.card.querySelectorAll('.emb-renombrar').forEach(b => {
        b.onclick = () => _embRenombrarCaja(Number(b.dataset.caja), num, () => _embGuiado());
    });
    if (mensaje) _embAviso(mensaje, '', 'ok');
}

async function _embImprimir(cajas) {
    const botones = _emb.card.querySelectorAll('#emb-imprimir, .emb-reimprimir');
    botones.forEach(b => { b.disabled = true; });
    _embAviso('Enviando a la impresora…', '', 'ok');
    const d = await _embPost(`/api/embalaje/orden/${encodeURIComponent(_emb.ordenId)}/carteles`, {
        operario: _emb.operario, operario_via: _emb.operarioVia, cajas: cajas || undefined,
    });
    if (!_emb) return;
    botones.forEach(b => { b.disabled = false; });
    if (!d.success) return _embAvisoDe(d);
    // Recargar para que salga como embalada, sin perder el mensaje.
    const r = await _embApi(`/api/embalaje/orden/${encodeURIComponent(_emb.ordenId)}`);
    if (!_emb) return;
    if (r.success) _emb.datos = r;
    _embGuiado(d.message);
}

// ==================== supervisor ====================

/** Pide que se identifique un supervisor para esta orden. Promise<bool>. */
function _embPedirSupervisor(titulo, explicacion) {
    return new Promise(resolve => {
        const terminar = ok => { _embParar(); resolve(ok); };
        const pintar = () => {
            _embMarco('🛡️', _escEmb(titulo), _embCabeceraOrden(), `
                <div class="ensayo-motivo">${_escEmb(explicacion)}</div>
                <div id="emb-sup">
                    <button type="button" class="ensayo-btn-sup" id="emb-sup-tarjeta">💳 Supervisor: pasar tarjeta</button>
                    <button type="button" class="ensayo-btn-link" id="emb-sup-clave">o identificarse con usuario y clave</button>
                </div>`,
                [{ id: 'emb-sup-cancelar', texto: '← Volver', accion: () => terminar(false) }]);
            _emb.card.querySelector('#emb-sup-tarjeta').onclick = tarjeta;
            _emb.card.querySelector('#emb-sup-clave').onclick = clave;
        };
        const autorizar = async credencial => {
            const d = await _embPost('/api/embalaje/supervisor', { orden_id: _emb.ordenId, ...credencial });
            if (!_emb) return;
            if (d.success) {
                if (_emb.datos) _emb.datos.autorizado_por = d.supervisor;
                return terminar(true);
            }
            pintar();
            _embAvisoDe(d);
        };
        const tarjeta = async () => {
            const d = await _embPost('/api/embalaje/supervisor/tarjeta', { orden_id: _emb.ordenId, puesto_id: _puestoEmb() });
            if (!_emb) return;
            if (!d.success) { _embAvisoDe(d); if (d.sin_lector) clave(); return; }
            const zona = _emb.card.querySelector('#emb-sup');
            zona.innerHTML = `<div class="ensayo-espera">💳 Supervisor: pasa tu tarjeta por el lector del puesto…
                                  <small id="emb-sup-msg"></small></div>
                              <button type="button" class="ensayo-btn-link" id="emb-sup-clave">o identificarse con usuario y clave</button>`;
            zona.querySelector('#emb-sup-clave').onclick = () => { _embParar(); clave(); };
            const limite = Date.now() + (d.segundos || 120) * 1000;
            _emb.temporizador = setInterval(async () => {
                const e = await _embApi(`/api/embalaje/supervisor/tarjeta/${encodeURIComponent(d.token)}`);
                if (!_emb) return;
                const msg = _emb.card.querySelector('#emb-sup-msg');
                if (e.estado === 'asignada') {
                    _embParar();
                    autorizar({ token: d.token });
                } else if ((e.estado && e.estado !== 'armada') || Date.now() > limite) {
                    _embParar();
                    pintar();
                    _embAviso('Se acabó el tiempo para pasar la tarjeta', 'Pulsa otra vez «pasar tarjeta»');
                } else if (msg && e.mensaje) {
                    msg.textContent = e.mensaje;
                }
            }, EMB_POLL_MS);
        };
        const clave = async () => {
            const r = await _embApi('/api/ensayos/supervisores');
            if (!_emb) return;
            const sups = r.supervisores || [];
            if (!sups.length) {
                return _embAviso('No hay supervisores con clave personal',
                                 'Admin → Operarios: dale el permiso «Supervisor de ensayos» y una clave');
            }
            const zona = _emb.card.querySelector('#emb-sup');
            zona.innerHTML = `
                <label class="ensayo-label">Supervisor
                    <select id="emb-sup-id">${sups.map(s =>
                        `<option value="${_escEmb(s.id)}">${_escEmb(s.nombre)}</option>`).join('')}</select></label>
                <label class="ensayo-label">Clave personal
                    <input type="password" id="emb-sup-pass" autocomplete="off"></label>
                <button type="button" class="ensayo-btn-sup" id="emb-sup-ok">Autorizar</button>`;
            const pass = zona.querySelector('#emb-sup-pass');
            pass.focus();
            const enviar = () => autorizar({ usuario: zona.querySelector('#emb-sup-id').value, clave: pass.value });
            zona.querySelector('#emb-sup-ok').onclick = enviar;
            pass.onkeydown = e => { if (e.key === 'Enter') enviar(); };
        };
        pintar();
    });
}
