// v3-modales.js — Operario y modales wizard: bono, puesto, máquina y terminal.
// Parte del antiguo main-v3.js (troceado sin cambios de código).
// Los ficheros v3-*.js comparten el ámbito global y se cargan en orden desde index-v3.html.

async function confirmarOperario() {
    const input = document.getElementById('input-operario');
    const errorDiv = document.getElementById('modal-operario-error');
    const valor = input ? input.value.trim() : '';

    if (!valor) {
        errorDiv.textContent = 'Selecciona tu operario de la lista.';
        errorDiv.classList.remove('hidden');
        input.focus();
        return;
    }

    errorDiv.classList.add('hidden');

    // Login exclusivo: el servidor rechaza si el operario ya está dentro
    // del módulo desde otro puesto.
    const btn = document.querySelector('.btn-confirmar-operario');
    if (btn) btn.disabled = true;
    try {
        const r = await fetch('/api/operarios/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre: valor })
        });
        const data = await r.json();
        if (!data.success) {
            errorDiv.textContent = data.error || 'No se pudo entrar con ese operario.';
            errorDiv.classList.remove('hidden');
            input.focus();
            return;
        }
        operarioLoginId = data.login_id;
        _iniciarLatidoOperario();
    } catch (_) {
        // Sin respuesta del servidor: dejar pasar para no bloquear el trabajo
        operarioLoginId = null;
    } finally {
        if (btn) btn.disabled = false;
    }

    sessionStorage.setItem('operario_actual', valor);
    _activarOperario(valor);
}

async function salirEngastadoV3() {
    if (!confirm('¿Cerrar sesión y salir del módulo de Engastado?')) return;

    // Cerrar login exclusivo del módulo en servidor.
    try {
        if (operarioLoginId) {
            await fetch('/api/operarios/logout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ login_id: operarioLoginId })
            });
        }
    } catch (_) { /* continuar igualmente */ }

    if (_latidoOperarioTimer) {
        clearInterval(_latidoOperarioTimer);
        _latidoOperarioTimer = null;
    }

    operarioActual = null;
    operarioLoginId = null;
    operarioTagUid = null;
    sessionStorage.removeItem('operario_actual');

    // beforeunload también limpia bloqueos/sesión de trabajo al abandonar.
    window.location.href = '/modules';
}

function _activarOperario(nombre) {
    operarioActual = nombre;

    // Cargar la tarjeta NFC del operario: es como se identifica luego en el
    // carro para confirmar recoger/devolver (además del botón del puesto).
    operarioTagUid = null;
    fetch('/api/operarios').then(r => r.json()).then(data => {
        const op = (data.operarios || []).find(o => o.nombre === nombre);
        operarioTagUid = (op && op.tag_uid) || null;
    }).catch(() => {});

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
        const bonos = data.success ? data.bonos.filter(b => b.estado === 'activo' && !b.finalizado) : [];

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
    ['modal-puesto', 'modal-maquina', 'modal-terminal', 'modal-carro', 'modal-regulacion'].forEach(mid => {
        const el = document.getElementById(mid);
        if (el) el.classList.toggle('hidden', mid !== id);
    });
}

function _cerrarModalesWizard() {
    ['modal-puesto', 'modal-maquina', 'modal-terminal', 'modal-carro', 'modal-regulacion'].forEach(mid => {
        const el = document.getElementById(mid);
        if (el) el.classList.add('hidden');
    });
}

function _actualizarUiPuestoBloqueado() {
    const btnModal = document.getElementById('btn-modal-cambiar-puesto');
    const btnPaso = document.getElementById('btn-volver-puestos');
    const bloqueado = !!puestoBloqueadoPorRfid;

    if (btnModal) {
        btnModal.style.display = bloqueado ? 'none' : '';
    }
    if (btnPaso) {
        btnPaso.style.display = bloqueado ? 'none' : '';
    }
}

function volverModalBonoDesdeModalPuesto() {
    document.getElementById('modal-puesto').classList.add('hidden');
    abrirModalBono();
}

async function abrirModalPuesto() {
    if (puestoBloqueadoPorRfid) {
        // El puesto ya está fijado por RFID asignado o por el propio PC.
        await abrirModalMaquina();
        return;
    }

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
    puestoBloqueadoPorRfid = false;
    _actualizarUiPuestoBloqueado();
    puestoSeleccionado = _puestosCache[idx];
    await abrirModalMaquina();
}

/**
 * Entrada por lector RFID asignado a un puesto (Admin -> Lectores RFID):
 * se salta el modal de elegir puesto y se va directa a máquina, igual que
 * si el operario lo hubiera elegido a mano. Si el puesto ya no existe o
 * está desactivado, cae al flujo manual normal en vez de dejar la pantalla
 * colgada.
 */
async function seleccionarPuestoAutomatico(puestoId) {
    try {
        const r = await fetch('/api/puestos');
        const data = await r.json();
        const puesto = data.success ? (data.puestos || []).find(p => p.id === puestoId && p.activo) : null;
        if (puesto) {
            puestoBloqueadoPorRfid = true;
            _actualizarUiPuestoBloqueado();
            puestoSeleccionado = puesto;
            await abrirModalMaquina();
            return;
        }
        console.warn('[RFID] Puesto asignado no encontrado o inactivo, se pide a mano:', puestoId);
    } catch (e) {
        console.warn('[RFID] Error resolviendo puesto asignado, se pide a mano:', e);
    }
    puestoBloqueadoPorRfid = false;
    _actualizarUiPuestoBloqueado();
    await abrirModalPuesto();
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

    // Si la máquina lleva regulación, mostrar popup de verificación primero
    if (maquinaSeleccionada.lleva_regulacion) {
        mostrarModalRegulacion();
    } else {
        await abrirModalTerminal();
    }
}

/** Muestra el modal de verificación de regulación */
function mostrarModalRegulacion() {
    // Ocultar resto de modales wizard
    ['modal-puesto', 'modal-maquina', 'modal-terminal', 'modal-carro'].forEach(mid => {
        const el = document.getElementById(mid);
        if (el) el.classList.add('hidden');
    });

    // Nombre de la máquina
    const nombreEl = document.getElementById('modal-reg-maquina-nombre');
    if (nombreEl) nombreEl.textContent = maquinaSeleccionada.nombre || '';

    // Botón PDF regulación
    const btnPdf = document.getElementById('btn-ver-regulacion');
    if (btnPdf) btnPdf.style.display = maquinaSeleccionada.pdf_regulacion ? '' : 'none';

    // Reset checkbox y botón confirmar
    const chk = document.getElementById('check-regulacion-ok');
    if (chk) chk.checked = false;
    const btnIniciar = document.getElementById('btn-iniciar-reg');
    if (btnIniciar) btnIniciar.disabled = true;

    document.getElementById('modal-regulacion').classList.remove('hidden');
}

/** Habilitar/deshabilitar botón confirmar según checkbox */
function toggleBtnIniciarReg(checked) {
    const btn = document.getElementById('btn-iniciar-reg');
    if (btn) btn.disabled = !checked;
}

/** Abre el PDF de regulación de la máquina actual */
function verPdfRegulacionV3() {
    if (maquinaSeleccionada?.id) {
        window.open(`/api/maquinas/${maquinaSeleccionada.id}/pdf-regulacion`, '_blank');
    }
}

/** Confirmar regulación y continuar al modal de terminales */
async function confirmarRegulacion() {
    document.getElementById('modal-regulacion').classList.add('hidden');
    await abrirModalTerminal();
}

/** Abre el PDF de instrucciones de la máquina actual (botón en cabecera) */
function verInstruccionesMaquina() {
    if (maquinaSeleccionada?.id && maquinaSeleccionada?.pdf_instrucciones) {
        window.open(`/api/maquinas/${maquinaSeleccionada.id}/pdf`, '_blank');
    }
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
    document.getElementById('modal-regulacion')?.classList.add('hidden');

    // Mostrar workspace y paso-trabajo
    document.getElementById('workspace-v3').classList.remove('hidden');
    document.getElementById('paso-trabajo').classList.remove('hidden');
    document.getElementById('paso-puesto').classList.add('hidden');
    document.getElementById('paso-maquina').classList.add('hidden');

    // Actualizar cabecera
    document.getElementById('maquina-seleccionada-nombre').textContent = maquinaSeleccionada.nombre;
    document.getElementById('ruta-puesto').textContent = puestoSeleccionado?.nombre || '';
    document.getElementById('ruta-maquina').textContent = maquinaSeleccionada.nombre;

    // Botón instrucciones — visible solo si tiene PDF
    const btnInstr = document.getElementById('btn-instrucciones-maquina');
    if (btnInstr) btnInstr.style.display = maquinaSeleccionada?.pdf_instrucciones ? '' : 'none';

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
