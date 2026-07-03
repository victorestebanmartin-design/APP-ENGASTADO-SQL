// v3-modales.js — Operario y modales wizard: bono, puesto, máquina y terminal.
// Parte del antiguo main-v3.js (troceado sin cambios de código).
// Los ficheros v3-*.js comparten el ámbito global y se cargan en orden desde index-v3.html.

function confirmarOperario() {
    const input = document.getElementById('input-operario');
    const errorDiv = document.getElementById('modal-operario-error');
    const valor = input ? input.value.trim() : '';

    if (!valor) {
        errorDiv.classList.remove('hidden');
        input.focus();
        return;
    }

    errorDiv.classList.add('hidden');
    sessionStorage.setItem('operario_actual', valor);
    _activarOperario(valor);
}

function _activarOperario(nombre) {
    operarioActual = nombre;

    // Ocultar modal de operario
    const modal = document.getElementById('modal-operario');
    if (modal) modal.classList.add('hidden');

    // Mostrar badge en el header
    const badge = document.getElementById('badge-operario');
    if (badge) {
        badge.textContent = `Operario: ${nombre}`;
        badge.classList.remove('hidden');
    }

    // Actualizar subtítulo del modal de bono con el nombre
    const subtitulo = document.getElementById('modal-bono-subtitulo');
    if (subtitulo) subtitulo.textContent = `Hola, ${nombre}. Elige cómo cargar el bono.`;

    // Mostrar modal de selección de bono
    abrirModalBono();
}

// ==================== MODAL DE BONO ====================

function abrirModalBono() {
    _mostrarVistaBono('metodo');
    const modalBono = document.getElementById('modal-bono');
    if (modalBono) modalBono.classList.remove('hidden');
}

function _mostrarVistaBono(vista) {
    ['metodo', 'input', 'lista'].forEach(v => {
        const el = document.getElementById(`modal-bono-${v}`);
        if (el) el.classList.toggle('hidden', v !== vista);
    });
    if (vista === 'input') {
        setTimeout(() => {
            const inp = document.getElementById('modal-input-bono');
            if (inp) inp.focus();
        }, 50);
    }
}

function mostrarInputBono() {
    document.getElementById('modal-bono-error').classList.add('hidden');
    document.getElementById('modal-input-bono').value = '';
    _mostrarVistaBono('input');

    const inp = document.getElementById('modal-input-bono');
    inp.onkeypress = (e) => { if (e.key === 'Enter') confirmarBonoCodigo(); };
}

async function mostrarListaBonosModal() {
    _mostrarVistaBono('lista');
    const contenido = document.getElementById('modal-bonos-lista-contenido');
    contenido.innerHTML = '<p class="modal-bonos-cargando">Cargando bonos...</p>';

    try {
        const response = await fetch('/api/bonos');
        const data = await response.json();
        const bonos = data.success ? data.bonos.filter(b => b.estado === 'activo') : [];

        if (bonos.length === 0) {
            contenido.innerHTML = '<p class="modal-bonos-vacio">No hay bonos activos disponibles.</p>';
            return;
        }

        contenido.innerHTML = bonos.map(bono => `
            <div class="modal-bono-item" onclick="seleccionarBonoDesdeModal('${bono.nombre}')">
                <div>
                    <div class="modal-bono-item-nombre">${bono.nombre}</div>
                    <div class="modal-bono-item-fecha">
                        Creado: ${new Date(bono.fecha_creacion).toLocaleDateString('es-ES')}
                    </div>
                </div>
                <span class="modal-bono-item-arrow">▶</span>
            </div>
        `).join('');
    } catch {
        contenido.innerHTML = '<p class="modal-bonos-vacio">Error al cargar los bonos.</p>';
    }
}

function volverMetodoBono() {
    _mostrarVistaBono('metodo');
}

async function confirmarBonoCodigo() {
    const inp = document.getElementById('modal-input-bono');
    const errorDiv = document.getElementById('modal-bono-error');
    const valor = inp ? inp.value.trim() : '';

    if (!valor) {
        errorDiv.classList.remove('hidden');
        inp.focus();
        return;
    }
    errorDiv.classList.add('hidden');
    await seleccionarBonoDesdeModal(valor);
}

async function seleccionarBonoDesdeModal(nombreBono) {
    // Poner el valor en el input legacy y llamar a cargarBono()
    const inputLegacy = document.getElementById('codigo-bono');
    if (inputLegacy) inputLegacy.value = nombreBono;

    // Cerrar modal de bono
    const modalBono = document.getElementById('modal-bono');
    if (modalBono) modalBono.classList.add('hidden');

    // Cargar el bono con la lógica existente
    await cargarBono();
}

// ==================== MODALES WIZARD: PUESTO / MÁQUINA / TERMINAL ====================

function _mostrarModalWizard(id) {
    ['modal-puesto', 'modal-maquina', 'modal-terminal', 'modal-carro'].forEach(mid => {
        const el = document.getElementById(mid);
        if (el) el.classList.toggle('hidden', mid !== id);
    });
}

function _cerrarModalesWizard() {
    ['modal-puesto', 'modal-maquina', 'modal-terminal', 'modal-carro'].forEach(mid => {
        const el = document.getElementById(mid);
        if (el) el.classList.add('hidden');
    });
}

function volverModalBonoDesdeModalPuesto() {
    document.getElementById('modal-puesto').classList.add('hidden');
    abrirModalBono();
}

async function abrirModalPuesto() {
    _mostrarModalWizard('modal-puesto');

    const subtitulo = document.getElementById('modal-puesto-subtitulo');
    if (subtitulo && bonoActual) subtitulo.textContent = `Bono: ${bonoActual.nombre}`;

    const lista = document.getElementById('modal-puesto-lista-contenido');
    lista.innerHTML = '<p class="modal-bonos-cargando">Cargando puestos...</p>';

    try {
        const [rPuestos, rTerminales] = await Promise.all([
            fetch('/api/puestos').then(r => r.json()),
            bonoActual
                ? fetch(`/api/bonos/${encodeURIComponent(bonoActual.nombre)}/terminales-disponibles`).then(r => r.json())
                : Promise.resolve({ success: false, terminales: [] })
        ]);

        const terminalesConDatos = rTerminales.success ? rTerminales.terminales : [];
        const todosActivos = rPuestos.success ? rPuestos.puestos.filter(p => p.activo) : [];

        // Calcular totales y filtrar puestos sin terminales en este bono
        const puestosConInfo = todosActivos.map((puesto, i) => {
            let total = 0, completados = 0;
            if (puesto.maquinas) {
                puesto.maquinas.filter(m => m.activo).forEach(m => {
                    const asignados = m.terminales_asignados || [];
                    const filtrados = terminalesConDatos.length > 0 ? asignados.filter(t => terminalesConDatos.includes(t)) : asignados;
                    total += filtrados.length;
                    if (window.progresoCompleto) {
                        completados += filtrados.filter(t => window.progresoCompleto[t]?.estado === 'completado').length;
                    }
                });
            }
            return { puesto, total, completados };
        }).filter(({ total }) => terminalesConDatos.length === 0 || total > 0);

        _puestosCache = puestosConInfo.map(({ puesto }) => puesto);

        if (_puestosCache.length === 0) {
            lista.innerHTML = '<p class="modal-bonos-vacio">No hay puestos con trabajo en este bono.</p>';
            return;
        }

        lista.innerHTML = puestosConInfo.map(({ puesto, total, completados }, i) => {
            const pct = total > 0 ? Math.round(completados / total * 100) : 0;
            const hecho = total > 0 && completados === total;

            return `<div class="modal-maquina-item${hecho ? ' completado' : ''}" onclick="seleccionarPuestoDesdeModal(${i})">
                <div class="modal-maquina-item-nombre">${hecho ? '✅ ' : ''}${puesto.nombre}</div>
                ${puesto.descripcion ? `<div class="modal-maquina-item-desc">${puesto.descripcion}</div>` : ''}
                ${total > 0 ? `<div class="modal-puesto-item-prog">
                    <div class="modal-prog-bar"><div class="modal-prog-fill" style="width:${pct}%;background:${hecho ? '#28a745' : '#0d6efd'}"></div></div>
                    <span class="modal-prog-text">${completados}/${total}</span>
                </div>` : ''}
            </div>`;
        }).join('');
        lista.innerHTML = `<div class="modal-maquina-grid">${lista.innerHTML}</div>`;

    } catch {
        lista.innerHTML = '<p class="modal-bonos-vacio">Error al cargar puestos.</p>';
    }
}

async function seleccionarPuestoDesdeModal(idx) {
    puestoSeleccionado = _puestosCache[idx];
    await abrirModalMaquina();
}

async function abrirModalMaquina() {
    _mostrarModalWizard('modal-maquina');

    const subtitulo = document.getElementById('modal-maquina-subtitulo');
    if (subtitulo && puestoSeleccionado) subtitulo.textContent = `Puesto: ${puestoSeleccionado.nombre}`;

    const lista = document.getElementById('modal-maquina-lista-contenido');
    lista.innerHTML = '<p class="modal-bonos-cargando">Cargando máquinas...</p>';

    if (bonoActual) await cargarProgresoDelBono(bonoActual.nombre);

    let terminalesConDatos = [];
    try {
        const r = await fetch(`/api/bonos/${encodeURIComponent(bonoActual.nombre)}/terminales-disponibles`);
        const d = await r.json();
        if (d.success) terminalesConDatos = d.terminales || [];
    } catch { /* continuar sin filtro */ }

    _maquinasCache = puestoSeleccionado?.maquinas
        ? puestoSeleccionado.maquinas.filter(m => {
            if (!m.activo) return false;
            const asignados = m.terminales_asignados || [];
            const filtrados = terminalesConDatos.length > 0 ? asignados.filter(t => terminalesConDatos.includes(t)) : asignados;
            return filtrados.length > 0;
        })
        : [];

    if (_maquinasCache.length === 0) {
        lista.innerHTML = '<p class="modal-bonos-vacio">Ninguna máquina de este puesto tiene terminales en el bono actual.</p>';
        return;
    }

    lista.innerHTML = _maquinasCache.map((maquina, i) => {
        const asignados = maquina.terminales_asignados || [];
        const filtrados = terminalesConDatos.length > 0 ? asignados.filter(t => terminalesConDatos.includes(t)) : asignados;
        const total = filtrados.length;
        let completados = 0;
        if (window.progresoCompleto) {
            completados = filtrados.filter(t => window.progresoCompleto[t]?.estado === 'completado').length;
        }
        const pct = total > 0 ? Math.round(completados / total * 100) : 0;
        const hecho = total > 0 && completados === total;

        return `<div class="modal-maquina-item${hecho ? ' completado' : ''}" onclick="seleccionarMaquinaDesdeModal(${i})">
            <div class="modal-maquina-item-nombre">${hecho ? '✅ ' : ''}${maquina.nombre}</div>
            ${maquina.modelo ? `<div class="modal-maquina-item-desc">${maquina.modelo}</div>` : ''}
            <div class="modal-puesto-item-prog">
                <div class="modal-prog-bar"><div class="modal-prog-fill" style="width:${pct}%;background:${hecho ? '#28a745' : '#0d6efd'}"></div></div>
                <span class="modal-prog-text">${completados}/${total}</span>
            </div>
        </div>`;
    }).join('');
    lista.innerHTML = `<div class="modal-maquina-grid">${lista.innerHTML}</div>`;
}

async function seleccionarMaquinaDesdeModal(idx) {
    maquinaSeleccionada = _maquinasCache[idx];
    await abrirModalTerminal();
}

async function abrirModalTerminal() {
    _mostrarModalWizard('modal-terminal');

    const subtitulo = document.getElementById('modal-terminal-subtitulo');
    if (subtitulo) subtitulo.textContent = `${puestoSeleccionado?.nombre || ''} → ${maquinaSeleccionada?.nombre || ''}`;

    const contenido = document.getElementById('modal-terminal-contenido');
    contenido.innerHTML = '<p class="modal-bonos-cargando">Cargando terminales...</p>';

    let terminalesConDatos = [];
    try {
        const r = await fetch(`/api/bonos/${encodeURIComponent(bonoActual.nombre)}/terminales-disponibles`);
        const d = await r.json();
        if (d.success) terminalesConDatos = d.terminales || [];
    } catch { /* continuar sin filtro */ }

    const todosAsignados = maquinaSeleccionada.terminales_asignados || [];
    terminalesAsignados = terminalesConDatos.length > 0
        ? todosAsignados.filter(t => terminalesConDatos.includes(t))
        : todosAsignados;

    await cargarProgresoMaquina();

    const total = terminalesAsignados.length;
    const numCompletados = terminalesCompletados.length;
    const pct = total > 0 ? Math.round(numCompletados / total * 100) : 0;

    if (total === 0) {
        contenido.innerHTML = '<p class="modal-bonos-vacio">No hay terminales disponibles en este bono.</p>';
        return;
    }

    contenido.innerHTML = `
        <div class="modal-terminal-progress">
            <div class="modal-terminal-progress-bar-wrap">
                <div class="modal-terminal-progress-bar" style="width:${pct}%"></div>
            </div>
            <span class="modal-terminal-progress-text">${numCompletados}/${total}</span>
        </div>
        <div class="modal-terminal-grid">
            ${terminalesAsignados.map(terminal => {
                const completado = terminalesCompletados.includes(terminal);
                const enProceso = !completado && terminalesEnProceso.includes(terminal);
                const enEspera  = !completado && !enProceso && terminalesEnEspera.includes(terminal);
                const clazz = completado ? 'completado' : enProceso ? 'en-proceso' : enEspera ? 'en-espera' : '';
                const etiqueta = completado ? '✅ Listo' : enProceso ? '🔵 En curso' : enEspera ? '🟡 Esperando' : '⬜ Pendiente';
                return `<div class="modal-terminal-item ${clazz}" ${!completado ? `onclick="seleccionarTerminalDesdeModal('${terminal}')"` : ''}>
                    <div class="modal-terminal-item-codigo">${terminal}</div>
                    <div class="modal-terminal-item-estado">${etiqueta}</div>
                </div>`;
            }).join('')}
        </div>`;
}

async function seleccionarTerminalDesdeModal(terminal) {
    _cerrarModalesWizard();

    // Mostrar workspace y paso-trabajo
    document.getElementById('workspace-v3').classList.remove('hidden');
    document.getElementById('paso-trabajo').classList.remove('hidden');
    document.getElementById('paso-puesto').classList.add('hidden');
    document.getElementById('paso-maquina').classList.add('hidden');

    // Actualizar cabecera
    document.getElementById('maquina-seleccionada-nombre').textContent = maquinaSeleccionada.nombre;
    document.getElementById('ruta-puesto').textContent = puestoSeleccionado?.nombre || '';
    document.getElementById('ruta-maquina').textContent = maquinaSeleccionada.nombre;

    // Indicador compacto con botón de cambio
    const container = document.getElementById('terminales-asignados');
    container.innerHTML = `<div style="text-align:center;padding:10px;color:#6c757d;font-size:0.9em;">
        Terminal activo: <strong style="color:#212529;">${terminal}</strong>
        &nbsp;<button type="button" onclick="abrirModalTerminal()" style="background:#f1f3f5;border:none;padding:5px 12px;border-radius:8px;cursor:pointer;font-size:0.88em;">🔄 Cambiar terminal</button>
    </div>`;

    setTimeout(() => {
        document.getElementById('paso-trabajo')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);

    await seleccionarTerminalTrabajo(terminal);
}

/**
 * Abrir dashboard de progreso con el bono actual
 */
