// ensayos.js — Pestañas de ensayos de tracción del módulo Calidad
// (templates/calidad.html): máquinas, matrices, fuerzas mínimas e historial.
// Cambiar la configuración pide sesión de administración (el servidor
// responde 401 si no la hay); consultar solo pide el permiso «calidad».
// Las pestañas del report están en calidad-report.js, que reutiliza esc/api.

const PUEDE_EDITAR = !!window.ENSAYOS_PUEDE_EDITAR;
let _maquinas = [];
let _historial = [];
let _fuerzas = [];

function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function aviso(texto, error = false) {
    const el = document.getElementById('ens-msg');
    el.textContent = texto;
    el.style.background = error ? '#dc3545' : '#198754';
    el.style.display = 'block';
    clearTimeout(aviso._t);
    aviso._t = setTimeout(() => { el.style.display = 'none'; }, error ? 5000 : 2500);
}

async function api(url, opciones = {}) {
    const r = await fetch(url, opciones);
    let d = {};
    try { d = await r.json(); } catch { /* sin cuerpo */ }
    if (r.status === 401) {
        aviso('Hace falta entrar como administrador para cambiar la configuración', true);
        throw new Error('401');
    }
    if (!r.ok || d.success === false) {
        aviso((d.motivo || d.message || 'Error') + (d.consejo ? ' — ' + d.consejo : ''), true);
        throw new Error(d.message || r.status);
    }
    return d;
}

function json(metodo, cuerpo) {
    return { method: metodo, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) };
}

// ==================== Pestañas ====================

document.querySelectorAll('.ens-tab').forEach(tab => {
    tab.onclick = () => {
        document.querySelectorAll('.ens-tab').forEach(t => t.classList.toggle('activa', t === tab));
        document.querySelectorAll('.ens-panel').forEach(p =>
            p.classList.toggle('activo', p.id === tab.dataset.panel));
        if (tab.dataset.panel === 'panel-historial' && !_historial.length) buscarHistorial();
    };
});

// ==================== Máquinas y matrices ====================

const SUGERIDA = { AUTOMATICA: 'diaria', 'SEMI-AUTOMATICA': 'diaria', MANUAL: 'mensual' };
const TIPO_TXT = { AUTOMATICA: 'Automática', 'SEMI-AUTOMATICA': 'Semiautomática', MANUAL: 'Manual' };

async function cargarMaquinas() {
    const d = await api('/api/ensayos/config');
    _maquinas = d.maquinas || [];
    pintarMaquinas();
    const sel = document.getElementById('h-maquina');
    sel.innerHTML = '<option value="">Todas</option>' +
        _maquinas.map(m => `<option value="${esc(m.id)}">${esc(m.nombre)}</option>`).join('');
}

function pintarMaquinas() {
    const cont = document.getElementById('lista-maquinas');
    if (!_maquinas.length) {
        cont.innerHTML = '<p class="ens-vacio">No hay máquinas. Créalas en Gestión de puestos.</p>';
        return;
    }
    const dis = PUEDE_EDITAR ? '' : 'disabled';
    cont.innerHTML = _maquinas.map(m => {
        const tipo = m.tipo_operacion || 'MANUAL';
        const sugerida = SUGERIDA[tipo];
        const opcion = (valor, texto) =>
            `<option value="${valor}" ${(m.ensayo_frecuencia || '') === valor ? 'selected' : ''}>${texto}${valor === sugerida ? ' (sugerida)' : ''}</option>`;
        const matrices = m.matrices.length
            ? m.matrices.map(z => `
                <span class="ens-chip">🔩 ${esc(z.nombre)}${z.codigo ? ` <small>(${esc(z.codigo)})</small>` : ''}
                    <button title="Renombrar" ${dis} onclick="renombrarMatriz('${esc(z.id)}')">✏️</button>
                    <button title="Quitar" ${dis} onclick="quitarMatriz('${esc(z.id)}')">✕</button></span>`).join(' ')
            : '<span class="ens-vacio">Sin matrices: todos sus terminales se ensayan a nivel de máquina.</span>';
        const terminales = m.terminales.length
            ? `<table class="ens-tabla" style="margin-top:10px"><thead><tr><th>Terminal</th><th>Matriz que lo engasta</th></tr></thead><tbody>
                ${m.terminales.map(t => `<tr><td>${esc(t.terminal_codigo)}</td><td>
                    <select ${dis || (m.matrices.length ? '' : 'disabled')}
                            onchange="asignarMatriz('${esc(m.id)}', '${esc(t.terminal_codigo)}', this.value)">
                        <option value="">— Sin matriz (nivel máquina) —</option>
                        ${m.matrices.map(z => `<option value="${esc(z.id)}" ${t.matriz_id === z.id ? 'selected' : ''}>${esc(z.nombre)}</option>`).join('')}
                    </select></td></tr>`).join('')}
               </tbody></table>`
            : '<p class="ens-vacio">Sin terminales asignados.</p>';
        return `
            <div class="ens-card">
                <div class="ens-maq-top">
                    <div><h3>${esc(m.nombre)}</h3>
                        <div class="ens-maq-sub">${esc(m.puesto_nombre || '')} · ${TIPO_TXT[tipo] || tipo}${m.lleva_regulacion ? ' · con regulación' : ''}</div></div>
                    <label class="ens-row">Ensayo:
                        <select ${dis} onchange="cambiarFrecuencia('${esc(m.id)}', this.value)">
                            ${opcion('', 'Sin ensayo')}${opcion('diaria', 'Diario (cada matriz, primer uso del día)')}${opcion('mensual', 'Mensual (primer uso del mes)')}
                        </select></label>
                </div>
                <div class="ens-row" style="margin-top:12px">
                    <strong>Matrices:</strong> ${matrices}
                    <button class="btn-secondary" ${dis} onclick="nuevaMatriz('${esc(m.id)}')">+ Matriz</button>
                </div>
                ${terminales}
            </div>`;
    }).join('');
}

async function cambiarFrecuencia(maquinaId, valor) {
    try {
        await api(`/api/ensayos/maquinas/${encodeURIComponent(maquinaId)}`, json('PUT', { ensayo_frecuencia: valor || null }));
        aviso('Frecuencia guardada');
    } catch { /* aviso ya mostrado */ }
    cargarMaquinas();
}

async function nuevaMatriz(maquinaId) {
    const nombre = prompt('Nombre de la matriz (p. ej. «A1» o «Puntera 1,5»):');
    if (!nombre || !nombre.trim()) return;
    const codigo = prompt('Código o nº de serie del aplicador (opcional):') || '';
    try {
        await api('/api/ensayos/matrices', json('POST', { maquina_id: maquinaId, nombre: nombre.trim(), codigo }));
        aviso('Matriz creada');
    } catch { /* aviso ya mostrado */ }
    cargarMaquinas();
}

async function renombrarMatriz(matrizId) {
    const z = _maquinas.flatMap(m => m.matrices).find(x => x.id === matrizId);
    const nombre = prompt('Nombre de la matriz:', z?.nombre || '');
    if (!nombre || !nombre.trim()) return;
    const codigo = prompt('Código o nº de serie (opcional):', z?.codigo || '') || '';
    try {
        await api(`/api/ensayos/matrices/${encodeURIComponent(matrizId)}`, json('PUT', { nombre: nombre.trim(), codigo }));
    } catch { /* aviso ya mostrado */ }
    cargarMaquinas();
}

async function quitarMatriz(matrizId) {
    if (!confirm('¿Quitar esta matriz? Sus terminales pasarán a ensayarse a nivel de máquina. Los ensayos ya hechos se conservan.')) return;
    try {
        await api(`/api/ensayos/matrices/${encodeURIComponent(matrizId)}`, { method: 'DELETE' });
    } catch { /* aviso ya mostrado */ }
    cargarMaquinas();
}

async function asignarMatriz(maquinaId, terminal, matrizId) {
    try {
        await api('/api/ensayos/terminal-matriz', json('PUT', { maquina_id: maquinaId, terminal, matriz_id: matrizId || null }));
        aviso('Guardado');
    } catch { cargarMaquinas(); }
}

// ==================== Fuerzas mínimas ====================

async function cargarFuerzas() {
    const d = await api('/api/ensayos/especificaciones');
    const filas = _fuerzas = d.especificaciones || [];
    const dis = PUEDE_EDITAR ? '' : 'disabled';
    document.getElementById('tabla-fuerzas').innerHTML = filas.length
        ? filas.map(f => `<tr>
            <td>${f.terminal_codigo ? esc(f.terminal_codigo) : '<em>Genérica</em>'}</td>
            <td>${esc(f.seccion)} mm²</td>
            <td><strong>${esc(f.fuerza_min_n)} N</strong></td>
            <td>${esc(f.norma || '')}</td>
            <td>${esc(f.instrucciones || '')}</td>
            <td style="white-space:nowrap">
                <button class="btn-secondary" ${dis} onclick="editarFuerza(${f.id})">✏️</button>
                <button class="btn-secondary" ${dis} onclick="borrarFuerza(${f.id})">🗑️</button></td>
          </tr>`).join('')
        : '<tr><td colspan="6" class="ens-vacio">Todavía no hay fuerzas mínimas. Sin ellas, una máquina con ensayo no deja engastar.</td></tr>';
}

function editarFuerza(id) {
    const f = _fuerzas.find(x => x.id === id);
    if (!f) return;
    document.getElementById('f-terminal').value = f.terminal_codigo || '';
    document.getElementById('f-seccion').value = f.seccion || '';
    document.getElementById('f-fuerza').value = f.fuerza_min_n ?? '';
    document.getElementById('f-norma').value = f.norma || '';
    document.getElementById('f-instr').value = f.instrucciones || '';
    document.getElementById('f-fuerza').focus();
}

document.getElementById('f-guardar').onclick = async () => {
    try {
        await api('/api/ensayos/especificaciones', json('POST', {
            terminal_codigo: document.getElementById('f-terminal').value,
            seccion: document.getElementById('f-seccion').value,
            fuerza_min_n: document.getElementById('f-fuerza').value,
            norma: document.getElementById('f-norma').value,
            instrucciones: document.getElementById('f-instr').value,
        }));
        aviso('Fuerza mínima guardada');
        ['f-terminal', 'f-seccion', 'f-fuerza', 'f-norma', 'f-instr'].forEach(id => {
            document.getElementById(id).value = '';
        });
        cargarFuerzas();
    } catch { /* aviso ya mostrado */ }
};

async function borrarFuerza(id) {
    if (!confirm('¿Borrar esta fuerza mínima? Los ensayos ya registrados conservan el valor con el que se hicieron.')) return;
    try {
        await api(`/api/ensayos/especificaciones/${id}`, { method: 'DELETE' });
    } catch { /* aviso ya mostrado */ }
    cargarFuerzas();
}

document.getElementById('f-excel').onchange = async (e) => {
    const fichero = e.target.files[0];
    if (!fichero) return;
    const datos = new FormData();
    datos.append('archivo', fichero);
    try {
        const d = await api('/api/ensayos/especificaciones/importar', { method: 'POST', body: datos });
        aviso(`${d.importadas} fuerzas importadas`);
        cargarFuerzas();
    } catch { /* aviso ya mostrado */ }
    e.target.value = '';
};

// ==================== Historial ====================

const TIPO_EV = { ensayo: 'Ensayo', regulacion: 'Regulación', decision: 'Decisión' };

async function buscarHistorial() {
    const qs = new URLSearchParams();
    [['desde', 'h-desde'], ['hasta', 'h-hasta'], ['maquina_id', 'h-maquina'], ['terminal', 'h-terminal'],
     ['tipo', 'h-tipo'], ['resultado', 'h-resultado']].forEach(([k, id]) => {
        const v = document.getElementById(id).value.trim();
        if (v) qs.set(k, v);
    });
    qs.set('limite', '2000');
    try {
        const d = await api('/api/ensayos/historial?' + qs.toString());
        _historial = d.eventos || [];
    } catch { return; }
    const tbody = document.getElementById('tabla-historial');
    tbody.innerHTML = _historial.length ? _historial.map(e => `<tr>
        <td style="white-space:nowrap">${esc(e.fecha)}</td>
        <td><span class="ens-tipo ${esc(e.tipo)}">${TIPO_EV[e.tipo] || esc(e.tipo)}</span></td>
        <td>${esc(e.maquina_nombre)}${e.matriz_nombre ? ' / ' + esc(e.matriz_nombre) : ''}</td>
        <td>${esc(e.terminal_codigo || '')}</td>
        <td>${e.seccion ? esc(e.seccion) + ' mm²' : ''}</td>
        <td>${e.fuerza_n != null ? esc(e.fuerza_n) + ' N' : ''}</td>
        <td>${e.fuerza_min_n != null ? esc(e.fuerza_min_n) + ' N' : ''}${e.norma ? `<br><small>${esc(e.norma)}</small>` : ''}</td>
        <td>${e.resultado ? `<span class="${e.resultado === 'OK' ? 'ens-ok' : 'ens-nok'}">${esc(e.resultado)}</span>` : ''}</td>
        <td>${esc(e.operario || '')}</td>
        <td>${e.supervisor ? esc(e.supervisor) + ` <small>(${esc(e.supervisor_via)})</small><br>` : ''}${e.decision ? (e.decision === 'continuar' ? '➡️ Continuar' : '🔁 Repetir') : ''}</td>
        <td>${esc(e.comentario || '')}</td>
    </tr>`).join('') : '<tr><td colspan="11" class="ens-vacio">Sin registros con esos filtros.</td></tr>';
}

document.getElementById('h-buscar').onclick = buscarHistorial;

document.getElementById('h-csv').onclick = () => {
    if (!_historial.length) { aviso('No hay nada que exportar', true); return; }
    const columnas = ['fecha', 'tipo', 'maquina_nombre', 'matriz_nombre', 'terminal_codigo', 'seccion',
                      'fuerza_n', 'fuerza_min_n', 'norma', 'resultado', 'origen', 'operario', 'bono',
                      'motivo', 'decision', 'supervisor', 'supervisor_via', 'comentario', 'id', 'ref_id'];
    const celda = v => {
        const s = String(v ?? '');
        return /[;"\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    // Punto y coma y BOM: es lo que abre bien el Excel en español.
    const csv = '﻿' + [columnas.join(';'), ..._historial.map(e => columnas.map(c => celda(e[c])).join(';'))].join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    a.download = `ensayos_traccion_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
};

cargarMaquinas().catch(() => {});
cargarFuerzas().catch(() => {});
