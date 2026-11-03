// v3-ensayos.js — Ensayo de tracción antes de engastar (lógica en app/ensayos.py).
//
// asegurarEnsayoTraccion(terminal) se llama al elegir terminal. Devuelve true
// si se puede seguir y false si el operario vuelve atrás.
//
// A diferencia de la puerta de la gaveta, aquí NO hay «continuar sin
// confirmar»: bloquear es justo lo que se busca. Si el servidor no responde
// se deja pasar, porque el bloqueo de verdad lo pone /api/datos_trabajo_v3 al
// cargar los paquetes (y entonces se vuelve a llamar aquí).

const ENSAYO_POLL_TARJETA_MS = 1000;

function _escEnsayo(valor) {
    return String(valor ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function _fmtN(n) {
    return (n === null || n === undefined) ? '—' : `${Number(n).toLocaleString('es-ES')} N`;
}

async function _estadoEnsayo(terminal) {
    const qs = new URLSearchParams({
        maquina_id: maquinaSeleccionada?.id || '',
        terminal: terminal,
        bono: bonoActual?.nombre || '',
    });
    const r = await fetch('/api/ensayos/estado?' + qs.toString());
    return await r.json();
}

async function asegurarEnsayoTraccion(terminal) {
    if (!maquinaSeleccionada?.id) return true;
    let est;
    try {
        est = await _estadoEnsayo(terminal);
    } catch (e) {
        console.warn('[ENSAYO] Sin respuesta del servidor:', e);
        return true;
    }
    if (!est || !est.success || !est.bloquea) return true;

    const overlay = document.createElement('div');
    overlay.className = 'modal-operario-overlay';
    overlay.id = 'modal-ensayo-traccion';
    overlay.innerHTML = '<div class="ensayo-card"></div>';
    document.body.appendChild(overlay);
    const card = overlay.querySelector('.ensayo-card');

    try {
        return await new Promise(resolve => {
            const ctx = { terminal, card, resolve, est, temporizador: null };
            _pintarEnsayo(ctx);
        });
    } finally {
        overlay.remove();
    }
}

function _pintarEnsayo(ctx) {
    clearInterval(ctx.temporizador);
    if (ctx.est.estado === 'nok_pendiente') {
        _pintarNok(ctx);
    } else {
        _pintarFormulario(ctx);
    }
}

function _cabeceraEnsayo(ctx, clase, icono, titulo) {
    const est = ctx.est;
    const donde = est.matriz
        ? `${_escEnsayo(est.maquina.nombre)} · Matriz <strong>${_escEnsayo(est.matriz.nombre)}</strong>`
        : _escEnsayo(est.maquina.nombre);
    return `
        <div class="ensayo-header ${clase}">
            <div class="ensayo-icon">${icono}</div>
            <h2>${titulo}</h2>
            <p>${donde} · Terminal <strong>${_escEnsayo(ctx.terminal)}</strong></p>
        </div>`;
}

// ---------- Falta el ensayo: instrucciones + resultado ----------

function _pintarFormulario(ctx) {
    const est = ctx.est;
    const secciones = est.secciones || [];
    if (ctx.seccion === undefined) {
        const primera = secciones.find(s => s.fuerza_min_n !== null) || secciones[0];
        ctx.seccion = primera ? primera.seccion : '';
    }
    const actual = secciones.find(s => s.seccion === ctx.seccion) || null;
    const minimo = actual ? actual.fuerza_min_n : null;

    const selector = secciones.length > 1
        ? `<div class="ensayo-secciones">${secciones.map(s => `
              <button type="button" class="ensayo-seccion ${s.seccion === ctx.seccion ? 'activa' : ''}"
                      data-seccion="${_escEnsayo(s.seccion)}">${_escEnsayo(s.seccion)} mm²</button>`).join('')}
           </div>
           <p class="ensayo-nota">Ensaya con la sección que vas a engastar primero.</p>`
        : (secciones.length === 1
            ? `<p class="ensayo-nota">Sección: <strong>${_escEnsayo(ctx.seccion)} mm²</strong></p>`
            : `<label class="ensayo-label">Sección (mm²)
                   <input type="text" id="ensayo-seccion-libre" inputmode="decimal"
                          value="${_escEnsayo(ctx.seccion)}" placeholder="1,5"></label>`);

    const instrucciones = (actual && actual.instrucciones)
        ? `<div class="ensayo-instr">${_escEnsayo(actual.instrucciones).replace(/\n/g, '<br>')}</div>`
        : `<ol class="ensayo-instr">
               <li>Engasta <strong>una probeta</strong> con esta matriz.</li>
               <li>Colócala en el dinamómetro y tira hasta que rompa.</li>
               <li>Escribe la fuerza de rotura.</li>
           </ol>`;

    const faltaMinimo = secciones.length > 0 && minimo === null;
    ctx.card.innerHTML = `
        ${_cabeceraEnsayo(ctx, '', '🧪', 'Ensayo de tracción obligatorio')}
        <div class="ensayo-body">
            <div class="ensayo-motivo">${_escEnsayo(est.motivo)}</div>
            ${selector}
            ${instrucciones}
            ${faltaMinimo
                ? `<div class="ensayo-error">No hay fuerza mínima para ${_escEnsayo(ctx.terminal)} a ${_escEnsayo(ctx.seccion)} mm².
                       <br><small>Pide a calidad que la añada en Ensayos tracción → Fuerzas mínimas.</small></div>`
                : (minimo !== null
                    ? `<div class="ensayo-minimo">Mínimo exigido: <strong>${_fmtN(minimo)}</strong>
                           ${actual.norma ? `<small>(${_escEnsayo(actual.norma)})</small>` : ''}</div>`
                    : '')}
            <label class="ensayo-label">Fuerza de rotura
                <div class="ensayo-input-row">
                    <input type="text" id="ensayo-fuerza" inputmode="decimal" autocomplete="off" placeholder="0">
                    <span>N</span>
                </div>
            </label>
            <div class="ensayo-aviso" id="ensayo-aviso" style="display:none"></div>
        </div>
        <div class="ensayo-footer">
            <button type="button" class="btn-volver-modal" id="ensayo-volver">← Cambiar terminal</button>
            <button type="button" class="ensayo-btn-ok" id="ensayo-registrar" ${faltaMinimo ? 'disabled' : ''}>Registrar ensayo</button>
        </div>`;

    ctx.card.querySelectorAll('.ensayo-seccion').forEach(b => {
        b.onclick = () => { ctx.seccion = b.dataset.seccion; _pintarFormulario(ctx); };
    });
    ctx.card.querySelector('#ensayo-volver').onclick = () => ctx.resolve(false);
    const input = ctx.card.querySelector('#ensayo-fuerza');
    input.focus();
    input.onkeydown = e => { if (e.key === 'Enter') ctx.card.querySelector('#ensayo-registrar').click(); };
    ctx.card.querySelector('#ensayo-registrar').onclick = () => _registrarEnsayo(ctx);
}

async function _registrarEnsayo(ctx) {
    const aviso = ctx.card.querySelector('#ensayo-aviso');
    const boton = ctx.card.querySelector('#ensayo-registrar');
    const libre = ctx.card.querySelector('#ensayo-seccion-libre');
    if (libre) ctx.seccion = libre.value.trim();
    const fuerza = ctx.card.querySelector('#ensayo-fuerza').value.trim();
    if (!fuerza) {
        _avisoEnsayo(aviso, 'Escribe la fuerza que marca el dinamómetro.');
        return;
    }
    boton.disabled = true;
    try {
        const r = await fetch('/api/ensayos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                maquina_id: maquinaSeleccionada.id, terminal: ctx.terminal,
                seccion: ctx.seccion, fuerza_n: fuerza, origen: 'manual',
                operario: operarioActual || '', bono: bonoActual?.nombre || '',
            }),
        });
        const d = await r.json();
        if (!d.success) {
            _avisoEnsayo(aviso, d.motivo || d.message || 'No se ha podido registrar', d.consejo);
            boton.disabled = false;
            return;
        }
        const e = d.ensayo;
        if (e.resultado === 'OK') {
            ctx.card.innerHTML = `
                ${_cabeceraEnsayo(ctx, 'ok', '✅', 'Ensayo superado')}
                <div class="ensayo-body ensayo-resultado">
                    <div class="ensayo-cifra ok">${_fmtN(e.fuerza_n)}</div>
                    <p>Mínimo ${_fmtN(e.fuerza_min_n)}. Queda registrado: puedes engastar.</p>
                </div>`;
            setTimeout(() => ctx.resolve(true), 1500);
            return;
        }
        ctx.est = await _estadoEnsayo(ctx.terminal);
        _pintarEnsayo(ctx);
    } catch (err) {
        _avisoEnsayo(aviso, 'Sin conexión con el servidor', 'Vuelve a intentarlo');
        boton.disabled = false;
    }
}

function _avisoEnsayo(aviso, motivo, consejo) {
    aviso.innerHTML = _escEnsayo(motivo) + (consejo ? `<br><small>${_escEnsayo(consejo)}</small>` : '');
    aviso.style.display = 'block';
}

// ---------- NOK: espera al supervisor ----------

function _pintarNok(ctx) {
    const nok = ctx.est.nok;
    ctx.card.innerHTML = `
        ${_cabeceraEnsayo(ctx, 'nok', '⛔', 'Ensayo no superado')}
        <div class="ensayo-body">
            <div class="ensayo-resultado">
                <div class="ensayo-cifra nok">${_fmtN(nok.fuerza_n)}</div>
                <p>Mínimo ${_fmtN(nok.fuerza_min_n)} · ${_escEnsayo(nok.seccion)} mm² · ${_escEnsayo(nok.fecha)}</p>
            </div>
            <div class="ensayo-motivo">No se puede engastar. Avisa al supervisor: tiene que identificarse y decidir.</div>
            <div id="ensayo-supervisor">
                <button type="button" class="ensayo-btn-sup" id="ensayo-tarjeta">💳 Supervisor: pasar tarjeta</button>
                <button type="button" class="ensayo-btn-link" id="ensayo-clave">o identificarse con usuario y clave</button>
            </div>
            <div class="ensayo-aviso" id="ensayo-aviso" style="display:none"></div>
        </div>
        <div class="ensayo-footer">
            <button type="button" class="btn-volver-modal" id="ensayo-volver">← Cambiar terminal</button>
        </div>`;
    ctx.card.querySelector('#ensayo-volver').onclick = () => { clearInterval(ctx.temporizador); ctx.resolve(false); };
    ctx.card.querySelector('#ensayo-tarjeta').onclick = () => _esperarTarjetaSupervisor(ctx);
    ctx.card.querySelector('#ensayo-clave').onclick = () => _pedirClaveSupervisor(ctx);
}

async function _esperarTarjetaSupervisor(ctx) {
    const zona = ctx.card.querySelector('#ensayo-supervisor');
    const aviso = ctx.card.querySelector('#ensayo-aviso');
    aviso.style.display = 'none';
    let d;
    try {
        const r = await fetch(`/api/ensayos/${encodeURIComponent(ctx.est.nok.id)}/supervisor/tarjeta`,
                              { method: 'POST' });
        d = await r.json();
    } catch {
        _avisoEnsayo(aviso, 'Sin conexión con el servidor', 'Vuelve a intentarlo');
        return;
    }
    if (!d.success) {
        _avisoEnsayo(aviso, d.motivo || d.message, d.consejo);
        if (d.consejo && d.consejo.includes('clave')) _pedirClaveSupervisor(ctx);
        return;
    }
    const limite = Date.now() + (d.segundos || 120) * 1000;
    zona.innerHTML = `<div class="ensayo-espera">💳 Supervisor: pasa tu tarjeta por el lector del puesto…
                          <small id="ensayo-espera-msg"></small></div>
                      <button type="button" class="ensayo-btn-link" id="ensayo-clave">o identificarse con usuario y clave</button>`;
    zona.querySelector('#ensayo-clave').onclick = () => { clearInterval(ctx.temporizador); _pedirClaveSupervisor(ctx); };
    ctx.temporizador = setInterval(async () => {
        try {
            const r = await fetch(`/api/ensayos/supervisor/tarjeta/${encodeURIComponent(d.token)}`);
            const e = await r.json();
            const msg = zona.querySelector('#ensayo-espera-msg');
            if (e.estado === 'asignada') {
                clearInterval(ctx.temporizador);
                _pintarDecision(ctx, { token: d.token }, e.supervisor);
            } else if (e.estado !== 'armada' || Date.now() > limite) {
                clearInterval(ctx.temporizador);
                _pintarNok(ctx);
                _avisoEnsayo(ctx.card.querySelector('#ensayo-aviso'),
                             'Se acabó el tiempo para pasar la tarjeta', 'Pulsa otra vez «pasar tarjeta»');
            } else if (msg && e.mensaje) {
                msg.textContent = e.mensaje;   // p. ej. «X no tiene permiso de supervisor»
            }
        } catch { /* reintenta en el siguiente tick */ }
    }, ENSAYO_POLL_TARJETA_MS);
}

async function _pedirClaveSupervisor(ctx) {
    const zona = ctx.card.querySelector('#ensayo-supervisor');
    let supervisores = [];
    try {
        const r = await fetch('/api/ensayos/supervisores');
        supervisores = (await r.json()).supervisores || [];
    } catch { /* lista vacía */ }
    if (!supervisores.length) {
        _avisoEnsayo(ctx.card.querySelector('#ensayo-aviso'),
                     'No hay supervisores con clave personal',
                     'Admin → Operarios: dale el permiso «Supervisor de ensayos» y una clave');
        return;
    }
    zona.innerHTML = `
        <label class="ensayo-label">Supervisor
            <select id="ensayo-sup-id">${supervisores.map(s =>
                `<option value="${_escEnsayo(s.id)}">${_escEnsayo(s.nombre)}</option>`).join('')}</select></label>
        <label class="ensayo-label">Clave personal
            <input type="password" id="ensayo-sup-clave" autocomplete="off"></label>
        <button type="button" class="ensayo-btn-sup" id="ensayo-sup-ok">Identificarse</button>`;
    zona.querySelector('#ensayo-sup-clave').focus();
    zona.querySelector('#ensayo-sup-ok').onclick = () => {
        const sel = zona.querySelector('#ensayo-sup-id');
        _pintarDecision(ctx, { usuario: sel.value, clave: zona.querySelector('#ensayo-sup-clave').value },
                        sel.options[sel.selectedIndex].text);
    };
}

function _pintarDecision(ctx, credencial, supervisor) {
    const zona = ctx.card.querySelector('#ensayo-supervisor');
    zona.innerHTML = `
        <div class="ensayo-sup-nombre">Supervisor: <strong>${_escEnsayo(supervisor)}</strong></div>
        <label class="ensayo-label">Comentario <small>(obligatorio para continuar)</small>
            <textarea id="ensayo-comentario" rows="2" maxlength="500"></textarea></label>
        <div class="ensayo-decision">
            <button type="button" class="ensayo-btn-repetir" data-d="repetir">🔁 Repetir ensayo</button>
            <button type="button" class="ensayo-btn-continuar" data-d="continuar">➡️ Continuar hoy</button>
        </div>`;
    zona.querySelectorAll('[data-d]').forEach(b => {
        b.onclick = () => _enviarDecision(ctx, credencial, b.dataset.d);
    });
}

async function _enviarDecision(ctx, credencial, decision) {
    const aviso = ctx.card.querySelector('#ensayo-aviso');
    const comentario = ctx.card.querySelector('#ensayo-comentario').value.trim();
    try {
        const r = await fetch(`/api/ensayos/${encodeURIComponent(ctx.est.nok.id)}/decision`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...credencial, decision, comentario, operario: operarioActual || '' }),
        });
        const d = await r.json();
        if (!d.success) {
            _avisoEnsayo(aviso, d.motivo || d.message, d.consejo);
            // Tarjeta ya gastada o clave mal: hay que volver a identificarse
            if (r.status === 403 || r.status === 409) setTimeout(() => _reEstadoEnsayo(ctx), 2500);
            return;
        }
        if (decision === 'continuar') {
            ctx.resolve(true);
            return;
        }
        await _reEstadoEnsayo(ctx);
    } catch {
        _avisoEnsayo(aviso, 'Sin conexión con el servidor', 'Vuelve a intentarlo');
    }
}

async function _reEstadoEnsayo(ctx) {
    try {
        ctx.est = await _estadoEnsayo(ctx.terminal);
    } catch { return; }
    if (!ctx.est.bloquea) { ctx.resolve(true); return; }
    ctx.seccion = undefined;
    _pintarEnsayo(ctx);
}

// ---------- Regulación ----------

/** El operario ha regulado la máquina: el ensayo vigente deja de valer. */
async function avisarRegulacionEnsayo() {
    if (!maquinaSeleccionada?.id) return;
    if (!confirm('¿Has regulado la máquina?\n\nAntes de engastar tendrás que hacer un ensayo de tracción.')) return;
    try {
        await fetch('/api/ensayos/regulacion', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ maquina_id: maquinaSeleccionada.id, operario: operarioActual || '' }),
        });
    } catch (e) {
        mostrarMensaje('No se ha podido registrar la regulación', 'error');
        return;
    }
    await confirmarRegulacion();
}
