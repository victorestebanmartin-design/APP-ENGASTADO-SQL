// v3-no-poner.js — Aviso "este terminal no se pone en estos cables".
// El operario marca, en el paquete abierto, los cables en los que el terminal
// no va. Se crea una propuesta que un admin aprueba en Admin → Propuestas de
// engastado; al aprobarla se pone el '*' en el Excel y el terminal deja de
// pedirse. Mientras está pendiente no cambia nada: el paquete se sigue
// engastando como siempre.

function _escNoPoner(valor) {
    return String(valor == null ? '' : valor).replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function _cablesParaAviso(paquete) {
    const subs = paquete.es_grupo ? (paquete.sub_paquetes || []) : [paquete];
    const cables = [];
    subs.forEach(sub => {
        const detalles = sub.detalles_cables || {};
        ['de', 'para', 'doble'].forEach(grupo => (detalles[grupo] || []).forEach(detalle => {
            if (detalle.fila == null) return;
            const lados = grupo === 'doble' ? ['de', 'para'] : [grupo];
            lados.forEach(lado => cables.push({
                fila: detalle.fila, lado, cable: detalle.cable, elemento: sub.elemento,
                archivo: sub.archivo_excel || paquete.archivo_excel,
                doble: grupo === 'doble',
            }));
        }));
    });
    return cables;
}

async function abrirAvisoNoPoner() {
    const paquete = paquetesOrdenados[paqueteActualIndex];
    if (!paquete) return;
    const cables = _cablesParaAviso(paquete);
    const archivo = cables[0]?.archivo;
    if (!archivo) { mostrarMensaje('No hay cables que señalar en este paquete', 'warning'); return; }
    const etiquetaPaquete = paquete.es_grupo ? `Serie ${paquete.grupo_serie}` : `${paquete.elemento} (${paquete.cod_cable})`;

    let pedidos = new Set();
    try {
        const r = await fetch(`/api/engastado/propuestas/cables-pendientes?archivo=${encodeURIComponent(archivo)}&terminal=${encodeURIComponent(terminalActual)}`);
        const datos = await r.json();
        if (datos.success) pedidos = new Set(datos.cables.map(c => `${c.fila}|${c.lado}`));
    } catch (e) { /* sin la lista se puede avisar igual; el servidor rechaza duplicados */ }

    document.getElementById('modal-no-poner')?.remove();
    const overlay = document.createElement('div');
    overlay.id = 'modal-no-poner';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);display:flex;justify-content:center;align-items:center;z-index:10050;padding:16px;box-sizing:border-box;';
    // Enter en este diálogo no debe pasar al siguiente paquete (handlerEnterPaquete escucha en document)
    overlay.addEventListener('keypress', e => e.stopPropagation());

    const chips = cables.map((c, i) => {
        const clave = `${c.fila}|${c.lado}`;
        const lado = c.lado === 'de' ? 'liso' : 'guion';
        const pedido = pedidos.has(clave);
        return `<button type="button" data-indice="${i}" ${pedido ? 'disabled' : ''} class="np-chip"
            style="padding:10px 14px;border-radius:8px;border:2px solid #ced4da;background:${pedido ? '#f1f3f5' : 'white'};color:#212529;font-weight:800;font-size:1em;cursor:${pedido ? 'not-allowed' : 'pointer'};touch-action:manipulation;${pedido ? 'text-decoration:line-through;opacity:.6;' : ''}">
            ${_escNoPoner(c.cable)}<span style="display:block;font-size:0.72em;font-weight:600;color:#6c757d;">${paquete.es_grupo ? _escNoPoner(c.elemento) + ' · ' : ''}lado ${lado}${pedido ? ' · ya avisado' : ''}</span>
        </button>`;
    }).join('');

    overlay.innerHTML = `
        <form id="np-form" style="background:white;border-radius:14px;max-width:640px;width:100%;max-height:calc(100dvh - 32px);overflow:auto;padding:22px;box-sizing:border-box;">
            <h2 style="margin:0 0 6px;font-size:1.3em;">🚫 ¿En qué cables NO va el terminal ${_escNoPoner(terminalActual)}?</h2>
            <p style="margin:0 0 14px;color:#495057;font-size:0.92em;">Paquete <strong>${_escNoPoner(etiquetaPaquete)}</strong>. Toca los cables y envía el aviso: lo revisa un administrador. <strong>Hasta que lo apruebe, el terminal se sigue pidiendo.</strong></p>
            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;">${chips}</div>
            <button type="button" id="np-todos" style="padding:6px 12px;font-size:0.85em;background:#f8f9fa;border:1.5px solid #ced4da;border-radius:8px;cursor:pointer;">Marcar todos</button>
            <fieldset style="margin:16px 0 8px;border:1px solid #dee2e6;border-radius:8px;padding:10px 14px;">
                <legend style="font-weight:700;font-size:0.92em;">Motivo</legend>
                ${['Plano / documentacion', 'Indicacion del cliente', 'Otros'].map((m, i) => `
                    <label style="display:block;padding:6px 0;cursor:pointer;"><input type="radio" name="np-motivo" value="${m}" ${i === 0 ? 'checked' : ''}> ${m === 'Plano / documentacion' ? 'Plano / documentación' : m === 'Indicacion del cliente' ? 'Indicación del cliente' : 'Otros'}</label>`).join('')}
                <textarea id="np-detalle" rows="2" maxlength="1900" placeholder="Detalle (obligatorio en Otros)" style="width:100%;box-sizing:border-box;margin-top:6px;padding:8px;border:1px solid #ced4da;border-radius:6px;font:inherit;"></textarea>
            </fieldset>
            <p id="np-error" role="alert" style="color:#b42318;min-height:1.2em;margin:6px 0;"></p>
            <div style="display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap;">
                <button type="button" id="np-cancelar" style="padding:12px 20px;background:white;border:1.5px solid #ced4da;border-radius:8px;cursor:pointer;font-weight:600;">Cancelar</button>
                <button type="submit" id="np-enviar" style="padding:12px 20px;background:#b42318;color:white;border:none;border-radius:8px;cursor:pointer;font-weight:700;">Enviar aviso</button>
            </div>
        </form>`;
    document.body.appendChild(overlay);

    const marcados = new Set();
    const pintar = boton => {
        const activo = marcados.has(Number(boton.dataset.indice));
        boton.style.background = activo ? '#fde2e1' : 'white';
        boton.style.borderColor = activo ? '#b42318' : '#ced4da';
    };
    overlay.querySelectorAll('.np-chip:not([disabled])').forEach(boton => boton.addEventListener('click', () => {
        const i = Number(boton.dataset.indice);
        marcados.has(i) ? marcados.delete(i) : marcados.add(i);
        pintar(boton);
    }));
    overlay.querySelector('#np-todos').addEventListener('click', () => {
        const libres = [...overlay.querySelectorAll('.np-chip:not([disabled])')];
        const todos = libres.every(b => marcados.has(Number(b.dataset.indice)));
        libres.forEach(b => { todos ? marcados.delete(Number(b.dataset.indice)) : marcados.add(Number(b.dataset.indice)); pintar(b); });
    });
    overlay.querySelector('#np-cancelar').addEventListener('click', () => overlay.remove());
    overlay.querySelector('#np-form').addEventListener('submit', async evento => {
        evento.preventDefault();
        const error = overlay.querySelector('#np-error');
        if (!marcados.size) { error.textContent = 'Toca al menos un cable.'; return; }
        const enviar = overlay.querySelector('#np-enviar');
        enviar.disabled = true;
        try {
            const r = await fetch('/api/engastado/propuestas', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    archivo, terminal: terminalActual, paquete: etiquetaPaquete,
                    cables: [...marcados].map(i => ({ fila: cables[i].fila, lado: cables[i].lado })),
                    motivo_categoria: overlay.querySelector('input[name=np-motivo]:checked').value,
                    motivo: overlay.querySelector('#np-detalle').value,
                }),
            });
            const datos = await r.json();
            if (!r.ok) throw new Error(datos.error || 'No se pudo enviar el aviso');
            overlay.querySelector('#np-form').innerHTML = `
                <div style="text-align:center;padding:20px 8px;">
                    <div style="font-size:2.4em;">✅</div>
                    <p style="font-size:1.15em;font-weight:700;margin:8px 0;">Aviso enviado al administrador</p>
                    <p style="color:#495057;margin:0;">Sigue engastando el paquete como está hasta que se apruebe.</p>
                </div>`;
            setTimeout(() => overlay.remove(), 2500);
        } catch (e) {
            error.textContent = e.message;
            enviar.disabled = false;
        }
    });
}
