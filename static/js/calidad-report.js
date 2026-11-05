// calidad-report.js — Pestañas de report del módulo Calidad (templates/calidad.html).
// Trazabilidad de engastado (/api/report/progreso, app/routes/reports.py)
// cruzada con los ensayos de tracción del mismo bono, terminal u operario.
// Se carga después de ensayos.js y reutiliza sus esc() y api().

function _repFecha(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return esc(iso);
    return d.toLocaleDateString('es-ES') + ' ' + d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
}

function _repEstado(estado) {
    const e = estado || 'en_proceso';
    return `<span class="rep-estado ${e === 'completado' ? 'completado' : ''}">${esc(e.replace('_', ' '))}</span>`;
}

function _repCarros(carros) {
    const lista = (carros || []).map(String).filter(c => c !== '');
    return lista.length ? lista.map(c => 'Carro ' + esc(c)).join(', ') : '<span class="ens-vacio">sin carro concreto</span>';
}

function _repMaquinas(maquinas) {
    return (maquinas || []).map(esc).join('<br>');
}

function _repTabla(cols, filas, vacio) {
    if (!filas.length) return `<p class="ens-vacio">${vacio}</p>`;
    return `<table class="ens-tabla"><thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead>
        <tbody>${filas.map(f => `<tr>${f.map(c => `<td>${c || '<span class="ens-vacio">—</span>'}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

// Ensayos, regulaciones y decisiones del supervisor que casan con el filtro.
async function _repEnsayos(filtro) {
    let eventos = [];
    try {
        eventos = (await api('/api/ensayos/historial?limite=1000&' + new URLSearchParams(filtro))).eventos || [];
    } catch { return '<p class="ens-vacio">No se han podido cargar los ensayos.</p>'; }
    const filas = eventos.map(e => [
        `<span style="white-space:nowrap">${esc(e.fecha)}</span>`,
        `<span class="ens-tipo ${esc(e.tipo)}">${TIPO_EV[e.tipo] || esc(e.tipo)}</span>`,
        esc(e.maquina_nombre) + (e.matriz_nombre ? ' / ' + esc(e.matriz_nombre) : ''),
        esc(e.terminal_codigo || ''),
        e.fuerza_n != null ? `${esc(e.fuerza_n)} N <small>(mín. ${esc(e.fuerza_min_n)} N)</small>` : '',
        e.resultado ? `<span class="${e.resultado === 'OK' ? 'ens-ok' : 'ens-nok'}">${esc(e.resultado)}</span>` : '',
        esc(e.operario || ''),
        (e.supervisor ? esc(e.supervisor) + ': ' : '') +
            (e.decision ? (e.decision === 'continuar' ? '➡️ Continuar' : '🔁 Repetir') : '') +
            (e.comentario ? ` <small>«${esc(e.comentario)}»</small>` : ''),
    ]);
    return `<h3 class="ens-sub">🧪 Ensayos de tracción (${eventos.length})</h3>` +
        _repTabla(['Fecha', 'Tipo', 'Máquina / matriz', 'Terminal', 'Fuerza', 'Resultado', 'Operario', 'Supervisor'],
                  filas, 'Sin ensayos registrados.');
}

async function _repBuscar(contId, filtroProgreso, filtroEnsayos, pintar) {
    const cont = document.getElementById(contId);
    cont.innerHTML = '<p class="ens-vacio">Cargando…</p>';
    let progreso;
    try {
        progreso = await api('/api/report/progreso?' + new URLSearchParams(filtroProgreso));
    } catch { cont.innerHTML = '<p class="ens-vacio">No se ha podido cargar el report.</p>'; return; }
    cont.innerHTML = pintar(progreso.registros || []) + await _repEnsayos(filtroEnsayos);
}

document.getElementById('rep-bono-ver').onclick = () => {
    const bono = document.getElementById('rep-bono').value;
    if (!bono) { aviso('Selecciona un bono', true); return; }
    _repBuscar('rep-bono-res', { bono }, { bono }, regs =>
        `<h3 class="ens-sub" style="margin-top:0">🔌 Engastado (${regs.length} terminales)</h3>` +
        _repTabla(['Terminal', 'Máquina', 'Operario', 'Estado', 'Inicio', 'Última actualización', 'Carros'],
            regs.map(r => [`<code>${esc(r.terminal)}</code>`, _repMaquinas(r.maquinas), esc(r.operario), _repEstado(r.estado),
                           _repFecha(r.fecha_inicio), _repFecha(r.fecha_ultima_actualizacion), _repCarros(r.carros_completados)]),
            'Sin datos de engastado para este bono.'));
};

document.getElementById('rep-bono-pdf').onclick = () => {
    const bono = document.getElementById('rep-bono').value;
    if (!bono) { aviso('Selecciona un bono', true); return; }
    window.open(`/report/bono/${encodeURIComponent(bono)}/carros`, '_blank');
};

document.getElementById('rep-terminal-ver').onclick = () => {
    const terminal = document.getElementById('rep-terminal').value.trim().toUpperCase();
    if (!terminal) { aviso('Escribe un terminal', true); return; }
    _repBuscar('rep-terminal-res', { terminal }, { terminal }, regs =>
        `<h3 class="ens-sub" style="margin-top:0">📦 Engastado en ${regs.length} bono${regs.length !== 1 ? 's' : ''}</h3>` +
        _repTabla(['Bono', 'Máquina', 'Operario', 'Estado', 'Inicio', 'Última actualización'],
            regs.map(r => [`<code>${esc(r.bono)}</code>`, _repMaquinas(r.maquinas), esc(r.operario), _repEstado(r.estado),
                           _repFecha(r.fecha_inicio), _repFecha(r.fecha_ultima_actualizacion)]),
            'Sin registros de engastado para este terminal.'));
};
document.getElementById('rep-terminal').onkeydown = e => {
    if (e.key === 'Enter') document.getElementById('rep-terminal-ver').click();
};

document.getElementById('rep-operario-ver').onclick = () => {
    const operario = document.getElementById('rep-operario').value;
    if (!operario) { aviso('Selecciona un operario', true); return; }
    _repBuscar('rep-operario-res', { operario }, { operario }, regs =>
        `<h3 class="ens-sub" style="margin-top:0">🔌 Engastado (${regs.length})</h3>` +
        _repTabla(['Terminal', 'Bono', 'Máquina', 'Estado', 'Inicio', 'Última actualización'],
            regs.map(r => [`<code>${esc(r.terminal)}</code>`, `<code>${esc(r.bono)}</code>`, _repMaquinas(r.maquinas), _repEstado(r.estado),
                           _repFecha(r.fecha_inicio), _repFecha(r.fecha_ultima_actualizacion)]),
            'Sin registros de engastado para este operario.'));
};

async function cargarSelectoresReport() {
    try {
        const d = await api('/api/bonos');
        document.getElementById('rep-bono').innerHTML = '<option value="">— Seleccionar bono —</option>' +
            (d.bonos || []).map(b => `<option value="${esc(b.nombre)}">${esc(b.nombre)}</option>`).join('');
    } catch { /* aviso ya mostrado */ }
    try {
        // También los dados de baja: una auditoría pregunta por lo que hicieron.
        const d = await api('/api/operarios');
        document.getElementById('rep-operario').innerHTML = '<option value="">— Seleccionar operario —</option>' +
            (d.operarios || []).map(o =>
                `<option value="${esc(o.nombre)}">${esc(o.nombre)}${o.activo ? '' : ' (baja)'}</option>`).join('');
    } catch { /* aviso ya mostrado */ }
}

cargarSelectoresReport();
