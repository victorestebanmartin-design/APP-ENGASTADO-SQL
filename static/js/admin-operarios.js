// Admin -> Operarios: tabla, permisos, tarjetas y logins activos.

// ──────────────────────────────────────────────────────────────
//  OPERARIOS — CRUD
// ──────────────────────────────────────────────────────────────
// Cache de MODULOS_APP (cambia poco, se pide una sola vez)
let _modulosAppCache = null;
function _cargarModulosApp() {
    if (_modulosAppCache) return Promise.resolve(_modulosAppCache);
    return fetch('/api/modulos').then(r => r.json()).then(d => {
        _modulosAppCache = d.modulos || [];
        return _modulosAppCache;
    });
}

function configurarClaveMangueras(id) {
    const formulario = document.getElementById('op-credencial-form');
    formulario.dataset.id = id;
    document.getElementById('op-credencial-clave').value = '';
    document.getElementById('op-credencial-error').textContent = '';
    document.getElementById('op-credencial-dialog').showModal();
}
document.getElementById('op-credencial-dialog').addEventListener('close', function () {
    document.getElementById('op-credencial-clave').value = '';
});
document.getElementById('op-credencial-form').addEventListener('submit', async function (evento) {
    evento.preventDefault();
    const boton = evento.target.querySelector('[type=submit]');
    boton.disabled = true;
    try {
        const respuesta = await fetch('/api/operarios/' + evento.target.dataset.id + '/credencial-admin', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
                clave: document.getElementById('op-credencial-clave').value
            })
        });
        document.getElementById('op-credencial-clave').value = '';
        const datos = await respuesta.json();
        if (!respuesta.ok) throw new Error(datos.error || datos.message || 'No se pudo guardar.');
        document.getElementById('op-credencial-dialog').close();
        cargarOperariosAdmin();
    } catch (error) { document.getElementById('op-credencial-error').textContent = error.message; }
    finally { boton.disabled = false; }
});

// Todo texto que venga de la BD se escapa antes de meterlo en innerHTML:
// un nombre con HTML se ejecutaría aquí con la sesión de administración.
function _opEsc(valor) {
    return String(valor ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function cargarOperariosAdmin() {
    Promise.all([fetch('/api/operarios').then(r => r.json()), _cargarModulosApp()])
        .then(([data, modulos]) => {
            const cont = document.getElementById('op-lista-container');
            if (!cont) return;
            if (!data.operarios || data.operarios.length === 0) {
                cont.innerHTML = '<p class="instruccion">No hay operarios registrados. Añade uno arriba.</p>';
                return;
            }
            const filas = data.operarios.map(op => {
                // null = sin permisos guardados: todo marcado salvo los que
                // solo se dan a propósito (Admin, Generar bonos, Calidad,
                // Supervisor de ensayos; ver MODULOS_SOLO_EXPLICITOS).
                const permitidos = op.modulos_permitidos;
                const celdasModulos = modulos.map(m => {
                    const marcado = permitidos === null ? !m.explicito : permitidos.includes(m.slug);
                    return `<td class="op-celda-permiso">
                        <input type="checkbox" class="op-mod-check" data-op="${op.id}" data-slug="${_opEsc(m.slug)}"
                            title="${_opEsc(m.label)}" aria-label="${_opEsc(m.label)} para ${_opEsc(op.nombre)}"
                            onchange="cambiarPermisoOperario(this)" ${marcado ? 'checked' : ''}>
                    </td>`;
                }).join('');
                return `
                <tr id="op-row-${op.id}" class="${op.activo ? '' : 'op-inactivo'}" data-buscar="${_opEsc((op.nombre + ' ' + (op.numero_empleado || '') + ' ' + (op.tag_uid || '')).toLowerCase())}">
                    <td class="op-celda-numero">
                        <span id="op-numero-${op.id}" class="${op.numero_empleado ? '' : 'op-vacio'}">${_opEsc(op.numero_empleado || '—')}</span>
                        <input type="text" id="op-edit-numero-${op.id}" value="${_opEsc(op.numero_empleado || '')}" maxlength="20"
                            class="op-edit-input" style="display:none;width:90px;"
                            onkeypress="if(event.key==='Enter')guardarOperario('${op.id}')">
                    </td>
                    <td class="op-celda-nombre">
                        <span id="op-nombre-${op.id}">${_opEsc(op.nombre)}</span>
                        ${op.activo ? '' : '<span class="badge-op badge-op-inactivo">Inactivo</span>'}
                        <input type="text" id="op-edit-${op.id}" value="${_opEsc(op.nombre)}"
                            class="op-edit-input" style="display:none;width:170px;"
                            onkeypress="if(event.key==='Enter')guardarOperario('${op.id}')">
                    </td>
                    <td class="op-celda-tarjeta">
                        <span id="op-tag-${op.id}" class="${op.tag_uid ? '' : 'op-vacio'}" style="font-family:'DM Mono',monospace;">${op.tag_uid ? _opEsc(op.tag_uid) : 'Sin tarjeta'}</span>
                        <button onclick="capturarTagOperario('${op.id}')" class="btn-accion-edit" title="Asignar tarjeta con un lector RFID">📡</button>
                        ${op.tag_uid ? `<button onclick="quitarTagOperario('${op.id}')" class="btn-accion-del" title="Quitar tarjeta">🗑️</button>` : ''}
                        <div id="op-rfid-captura-${op.id}"></div>
                    </td>
                    ${celdasModulos}
                    <td class="op-celda-clave">
                        <button class="btn-accion-edit" type="button" onclick="configurarClaveMangueras('${op.id}')"
                            title="${op.clave_personal_configurada ? 'Tiene contraseña de administración. Pulsa para cambiarla' : 'Sin contraseña de administración. Pulsa para ponerla'}">
                            ${op.clave_personal_configurada ? '🔑' : '➕'}</button>
                    </td>
                    <td class="op-celda-acciones">
                        <span id="op-btns-${op.id}">
                            <button onclick="editarOperario('${op.id}')" class="btn-accion-edit" title="Editar nombre y número">✏️</button>
                            ${op.activo
                                ? `<button onclick="desactivarOperario('${op.id}')" class="btn-accion-del" title="Desactivar">🚫</button>`
                                : `<button onclick="activarOperario('${op.id}')" class="btn-accion-edit" title="Activar">✅</button>`
                            }
                        </span>
                        <span id="op-edit-btns-${op.id}" style="display:none;">
                            <button onclick="guardarOperario('${op.id}')" class="btn-primary" style="padding:4px 12px;font-size:0.85em;">Guardar</button>
                            <button onclick="cancelarEditarOperario('${op.id}')" class="btn-secondary" style="padding:4px 12px;font-size:0.85em;">Cancelar</button>
                        </span>
                    </td>
                </tr>`;
            }).join('');
            const cabecerasModulos = modulos.map(m =>
                `<th class="op-th-permiso" title="${_opEsc(m.label)}${m.explicito ? ' (solo si se marca a propósito)' : ''}"><span>${_opEsc(m.label)}</span></th>`
            ).join('');
            cont.innerHTML = `
                <div class="op-tabla-barra">
                    <input type="search" id="op-buscar" class="op-edit-input" placeholder="Buscar por nombre, número o tarjeta"
                        oninput="filtrarOperarios(this.value)">
                    <span class="instruccion">Los permisos se guardan al marcar la casilla.</span>
                </div>
                <div class="tabla-container op-tabla">
                    <table>
                        <thead>
                            <tr>
                                <th>Nº</th>
                                <th>Nombre</th>
                                <th>Tarjeta</th>
                                ${cabecerasModulos}
                                <th class="op-th-permiso" title="Contraseña de administración (para entrar en Admin con su nombre)"><span>Clave admin</span></th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>${filas}</tbody>
                    </table>
                </div>`;
            const buscar = document.getElementById('op-buscar');
            if (buscar && _opFiltro) { buscar.value = _opFiltro; filtrarOperarios(_opFiltro); }
        });
}

// El filtro sobrevive a las recargas de la tabla (asignar tarjeta, guardar...).
let _opFiltro = '';
function filtrarOperarios(texto) {
    _opFiltro = texto || '';
    const q = _opFiltro.trim().toLowerCase();
    document.querySelectorAll('#op-lista-container tbody tr').forEach(fila => {
        fila.style.display = !q || (fila.dataset.buscar || '').includes(q) ? '' : 'none';
    });
}

// Cada casilla se guarda al marcarla: se manda la fila entera, como hacía
// el antiguo botón «Guardar permisos». Dar Administración se confirma.
function cambiarPermisoOperario(casilla) {
    const id = casilla.dataset.op;
    if (casilla.dataset.slug === 'admin' && casilla.checked &&
        !confirm('¿Dar acceso a Administración a este operario?')) {
        casilla.checked = false;
        return;
    }
    const checks = document.querySelectorAll(`.op-mod-check[data-op="${id}"]`);
    const modulos_permitidos = Array.from(checks).filter(c => c.checked).map(c => c.dataset.slug);
    const celda = casilla.closest('td');
    casilla.disabled = true;
    fetch(`/api/operarios/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modulos_permitidos })
    }).then(r => r.json().then(data => ({ ok: r.ok, data }))).then(({ ok, data }) => {
        if (!ok || !data.success) throw new Error(data.error || data.message || 'No se pudo guardar');
        celda.classList.remove('op-guardado'); void celda.offsetWidth; celda.classList.add('op-guardado');
    }).catch(error => {
        casilla.checked = !casilla.checked;
        _opMsg('Permiso sin guardar: ' + error.message, 'error');
    }).finally(() => { casilla.disabled = false; });
}

// Logins activos (quién está dentro del módulo de engastado)
function cargarLoginsAdmin() {
    fetch('/api/operarios/logins')
        .then(r => r.json())
        .then(data => {
            const cont = document.getElementById('op-logins-container');
            if (!cont) return;
            if (!data.logins || data.logins.length === 0) {
                cont.innerHTML = '<p class="instruccion">Nadie está dentro del módulo ahora mismo.</p>';
                return;
            }
            const filas = data.logins.map(l => `
                <tr>
                    <td>${_opEsc(l.operario)}</td>
                    <td>${_opEsc((l.desde || '').replace('T', ' ').slice(0, 16))}</td>
                    <td>
                        <button onclick="liberarLoginAdmin('${l.id}')" class="btn-accion-del" title="Liberar login">🚪 Liberar</button>
                    </td>
                </tr>`).join('');
            cont.innerHTML = `
                <div class="tabla-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Operario</th>
                                <th>Dentro desde</th>
                                <th>Acciones</th>
                            </tr>
                        </thead>
                        <tbody>${filas}</tbody>
                    </table>
                </div>`;
        });
}

function liberarLoginAdmin(id) {
    if (!confirm('¿Liberar este login? El operario podrá volver a entrar desde cualquier puesto.')) return;
    fetch(`/api/operarios/logins/${id}/liberar`, { method: 'POST' })
        .then(r => r.json()).then(data => {
            if (data.success) { _opMsg('Login liberado.', 'ok'); cargarLoginsAdmin(); }
            else _opMsg(data.message || data.error || 'Error.', 'error');
        });
}

function crearOperario() {
    const input = document.getElementById('op-nuevo-nombre');
    const msg = document.getElementById('op-msg');
    const inputNumero = document.getElementById('op-nuevo-numero');
    const nombre = (input.value || '').trim();
    if (!nombre) { _opMsg('Introduce un nombre.', 'error'); return; }
    fetch('/api/operarios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre, numero_empleado: inputNumero.value })
    }).then(r => r.json()).then(data => {
        if (data.success) {
            input.value = '';
            inputNumero.value = '';
            _opMsg('Operario añadido.', 'ok');
            cargarOperariosAdmin();
        } else {
            _opMsg(data.error || 'Error al crear.', 'error');
        }
    });
}

function editarOperario(id) {
    document.getElementById('op-nombre-' + id).style.display = 'none';
    document.getElementById('op-edit-' + id).style.display = 'inline-block';
    document.getElementById('op-numero-' + id).style.display = 'none';
    document.getElementById('op-edit-numero-' + id).style.display = 'inline-block';
    document.getElementById('op-btns-' + id).style.display = 'none';
    document.getElementById('op-edit-btns-' + id).style.display = 'inline';
    document.getElementById('op-edit-' + id).focus();
}

function cancelarEditarOperario(id) {
    document.getElementById('op-nombre-' + id).style.display = 'inline';
    document.getElementById('op-edit-' + id).style.display = 'none';
    document.getElementById('op-numero-' + id).style.display = 'inline';
    document.getElementById('op-edit-numero-' + id).style.display = 'none';
    document.getElementById('op-btns-' + id).style.display = 'inline';
    document.getElementById('op-edit-btns-' + id).style.display = 'none';
}

function guardarOperario(id) {
    const nombre = (document.getElementById('op-edit-' + id).value || '').trim();
    const numero_empleado = document.getElementById('op-edit-numero-' + id).value;
    if (!nombre) return;
    fetch(`/api/operarios/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre, numero_empleado })
    }).then(r => r.json()).then(data => {
        if (data.success) { _opMsg('Guardado.', 'ok'); cargarOperariosAdmin(); }
        else _opMsg(data.error || 'Error.', 'error');
    });
}

function desactivarOperario(id) {
    if (!confirm('¿Desactivar este operario?')) return;
    fetch(`/api/operarios/${id}`, { method: 'DELETE' })
        .then(r => r.json()).then(data => {
            if (data.success) { _opMsg('Desactivado.', 'ok'); cargarOperariosAdmin(); }
            else _opMsg(data.error || 'Error.', 'error');
        });
}

function activarOperario(id) {
    fetch(`/api/operarios/${id}/activar`, { method: 'POST' })
        .then(r => r.json()).then(data => {
            if (data.success) { _opMsg('Activado.', 'ok'); cargarOperariosAdmin(); }
            else _opMsg(data.error || 'Error.', 'error');
        });
}

function _opMsg(texto, tipo) {
    const el = document.getElementById('op-msg');
    if (!el) return;
    el.textContent = texto;
    el.style.display = 'block';
    el.style.color = tipo === 'ok' ? '#22c55e' : '#ef4444';
    setTimeout(() => { el.style.display = 'none'; }, 3000);
}

// ── Asignar tarjeta NFC a un operario mediante un lector RFID elegido.
// El lector entra en modo de captura temporal y envía el UID al servidor. ──
let _opCapturaTimer = null;
let _opCapturaActual = null;
function _pararCapturaTagOperario(cancelarServidor) {
    if (_opCapturaTimer) { clearTimeout(_opCapturaTimer); _opCapturaTimer = null; }
    const anterior = _opCapturaActual;
    _opCapturaActual = null;
    if (cancelarServidor && anterior && anterior.token) {
        fetch(`/api/operarios/${anterior.id}/rfid/captura/${anterior.token}`, { method: 'DELETE' })
            .catch(() => {});
    }
}

function _opBotonCaptura(texto, clase, alPulsar) {
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.className = clase;
    boton.textContent = texto;
    boton.style.cssText = 'padding:4px 9px;font-size:0.8em;margin-left:5px;';
    boton.onclick = alPulsar;
    return boton;
}

async function capturarTagOperario(id) {
    _pararCapturaTagOperario(true);
    const control = document.getElementById('op-rfid-captura-' + id);
    if (!control) return;
    control.textContent = 'Buscando lectores conectados...';
    control.style.color = '#94a3b8';
    try {
        const resp = await fetch('/api/esp32/rfid/devices');
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'No se pudieron cargar los lectores');
        const conectados = (data.devices || []).filter(d => d.online);
        const lectores = conectados.filter(d => d.fw === data.firmware_version);
        control.innerHTML = '';
        if (!lectores.length) {
            control.textContent = conectados.length
                ? 'Los lectores conectados necesitan actualizarse antes de registrar tarjetas.'
                : 'No hay lectores RFID conectados.';
            control.style.color = '#f87171';
            return;
        }

        const selector = document.createElement('select');
        selector.style.cssText = 'padding:5px 8px;background:#0f172a;border:1px solid #475569;color:#f1f5f9;border-radius:5px;max-width:240px;';
        const opcionInicial = document.createElement('option');
        opcionInicial.value = '';
        opcionInicial.textContent = 'Elige un lector conectado';
        selector.appendChild(opcionInicial);
        lectores.forEach(lector => {
            const opcion = document.createElement('option');
            opcion.value = lector.id;
            opcion.textContent = `${lector.nombre || lector.id}${lector.puesto_nombre ? ' · ' + lector.puesto_nombre : ''}`;
            selector.appendChild(opcion);
        });
        control.appendChild(selector);
        control.appendChild(_opBotonCaptura('Preparar lector', 'btn-secondary', () => {
            if (!selector.value) {
                control.style.color = '#fbbf24';
                return;
            }
            _iniciarCapturaTagOperario(id, selector.value, control);
        }));
        control.appendChild(_opBotonCaptura('Cancelar', 'btn-secondary', () => { control.innerHTML = ''; }));
    } catch (error) {
        control.textContent = error.message || 'No se pudieron cargar los lectores.';
        control.style.color = '#f87171';
    }
}

async function _iniciarCapturaTagOperario(id, deviceId, control) {
    control.textContent = 'Enviando orden al lector...';
    control.style.color = '#60a5fa';
    try {
        const resp = await fetch(`/api/operarios/${id}/rfid/captura`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId })
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'No se pudo preparar el lector');
        const captura = { id, token: data.token, deviceId, vence: Date.now() + data.segundos * 1000 };
        _opCapturaActual = captura;
        _opMostrarCapturaArmada(control, captura);
    } catch (error) {
        control.textContent = error.message || 'No se pudo preparar el lector.';
        control.style.color = '#f87171';
    }
}

function _opMostrarCapturaArmada(control, captura) {
    if (_opCapturaActual !== captura) return;
    const restantes = Math.max(0, Math.ceil((captura.vence - Date.now()) / 1000));
    control.innerHTML = '';
    const texto = document.createElement('span');
    texto.textContent = `Lector preparado. Pasa la tarjeta (${restantes} s)`;
    texto.style.color = '#60a5fa';
    control.appendChild(texto);
    control.appendChild(_opBotonCaptura('Cancelar', 'btn-secondary', () => {
        _pararCapturaTagOperario(true);
        control.textContent = 'Captura cancelada.';
        control.style.color = '#94a3b8';
    }));
    _opCapturaTimer = setTimeout(() => _sondearCapturaTagOperario(control, captura), 1000);
}

async function _sondearCapturaTagOperario(control, captura) {
    if (_opCapturaActual !== captura) return;
    try {
        const resp = await fetch(`/api/operarios/${captura.id}/rfid/captura/${captura.token}`);
        const data = await resp.json();
        if (resp.ok && data.success && data.estado !== 'armada') {
            _pararCapturaTagOperario(false);
            control.textContent = data.mensaje || (data.estado === 'asignada' ? 'Tarjeta asignada.' : 'Captura finalizada.');
            control.style.color = data.estado === 'asignada' ? '#4ade80' : '#f87171';
            if (data.estado === 'asignada') _opMsg(`Tarjeta ${data.uid} asignada.`, 'ok');
            else _opMsg(data.mensaje || 'No se pudo asignar la tarjeta.', 'error');
            cargarOperariosAdmin();
            return;
        }
    } catch (e) { /* Un corte breve no cancela la captura; se vuelve a consultar. */ }
    if (Date.now() >= captura.vence) {
        _pararCapturaTagOperario(false);
        control.textContent = 'Se agotó el tiempo. Vuelve a intentarlo.';
        control.style.color = '#f87171';
        return;
    }
    _opMostrarCapturaArmada(control, captura);
}

function quitarTagOperario(id) {
    if (!confirm('¿Quitar la tarjeta de este operario?')) return;
    _pararCapturaTagOperario(true);
    fetch(`/api/operarios/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag_uid: null })
    }).then(r => r.json()).then(data => {
        if (data.success) { _opMsg('Tarjeta quitada.', 'ok'); }
        else _opMsg(data.error || 'Error.', 'error');
        cargarOperariosAdmin();
    });
}

adminAlAbrir('operarios', cargarOperariosAdmin);
adminAlAbrir('operarios', cargarLoginsAdmin);
