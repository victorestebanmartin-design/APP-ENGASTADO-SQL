// ================================
// GESTIÓN DE PUESTOS Y MÁQUINAS
// ================================

let dataPuestos = null;
let dataMaquinas = null;

// Estado PDF modal máquina
let _pdfPendiente = null;          // File object pendiente de subir
let _pdfMaquinaIdActual = null;    // ID de la máquina en edición
let _pdfRegPendiente = null;       // File PDF regulación pendiente de subir

// Cargar datos al iniciar
document.addEventListener('DOMContentLoaded', function() {
    cargarPuestos();
    cargarMaquinas();
    cargarAsignaciones();
});
// ================================
// GESTIÓN DE PUESTOS
// ================================

/**
 * Cargar lista de puestos
 */
async function cargarPuestos() {
    try {
        const response = await fetch('/api/puestos');
        const data = await response.json();
        
        if (data.success) {
            dataPuestos = data.puestos;
            mostrarListaPuestos(data.puestos);
        } else {
            document.getElementById('lista-puestos').innerHTML = '<p class="error">Error al cargar puestos</p>';
        }
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('lista-puestos').innerHTML = '<p class="error">Error de conexión</p>';
    }
}

/**
 * Mostrar lista de puestos
 */
function mostrarListaPuestos(puestos) {
    const container = document.getElementById('lista-puestos');
    
    if (puestos.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🏢</div>
                <h4>No hay puestos configurados</h4>
                <p>Crea el primer puesto de trabajo para comenzar a organizar tu planta.</p>
                <button class="btn btn-primary" onclick="mostrarModalPuesto()">
                    ➕ Crear Primer Puesto
                </button>
            </div>
        `;
        return;
    }
    
    container.innerHTML = `
        <div class="puestos-grid">
            ${puestos.map(puesto => `
                <div class="puesto-card" data-id="${puesto.id}">
                    <div class="puesto-header">
                        <h4>${puesto.nombre}</h4>
                        <div class="puesto-actions">
                            <button class="btn-icon" onclick="editarPuesto('${puesto.id}')" title="Editar">
                                ✏️
                            </button>
                            <button class="btn-icon" onclick="eliminarPuesto('${puesto.id}')" title="Eliminar">
                                🗑️
                            </button>
                        </div>
                    </div>
                    <p class="puesto-descripcion">${puesto.descripcion || 'Sin descripción'}</p>
                    <div class="puesto-stats">
                        <span class="stat">
                            ⚙️ ${puesto.maquinas ? puesto.maquinas.length : 0} máquinas
                        </span>
                        <span class="stat-status ${puesto.activo ? 'activo' : 'inactivo'}">
                            ${puesto.activo ? '✅ Activo' : '❌ Inactivo'}
                        </span>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

/**
 * Mostrar modal para crear/editar puesto
 */
function mostrarModalPuesto(puestoId = null) {
    const modal = document.getElementById('modal-puesto');
    const titulo = modal.querySelector('h3');
    
    if (puestoId) {
        titulo.textContent = 'Editar Puesto';
        const puesto = dataPuestos.find(p => p.id === puestoId);
        if (puesto) {
            document.getElementById('puesto-nombre').value = puesto.nombre;
            document.getElementById('puesto-descripcion').value = puesto.descripcion || '';
        }
    } else {
        titulo.textContent = 'Nuevo Puesto';
        document.getElementById('puesto-nombre').value = '';
        document.getElementById('puesto-descripcion').value = '';
    }
    
    modal.dataset.editId = puestoId || '';
    modal.classList.add('active');
}

/**
 * Guardar puesto
 */
async function guardarPuesto() {
    const nombre = document.getElementById('puesto-nombre').value.trim();
    const descripcion = document.getElementById('puesto-descripcion').value.trim();
    const editId = document.getElementById('modal-puesto').dataset.editId;
    
    if (!nombre) {
        alert('El nombre del puesto es obligatorio');
        return;
    }
    
    try {
        const url = editId ? `/api/puestos/${editId}` : '/api/puestos';
        const method = editId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                nombre: nombre,
                descripcion: descripcion
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            cerrarModal('modal-puesto');
            cargarPuestos();
            mostrarNotificacion(editId ? 'Puesto actualizado correctamente' : 'Puesto creado correctamente', 'success');
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al guardar el puesto');
    }
}

/**
 * Editar puesto
 */
function editarPuesto(puestoId) {
    mostrarModalPuesto(puestoId);
}

/**
 * Eliminar puesto
 */
async function eliminarPuesto(puestoId) {
    const puesto = dataPuestos.find(p => p.id === puestoId);
    const nombrePuesto = puesto ? puesto.nombre : 'este puesto';
    
    if (!confirm(`¿Estás seguro de que quieres eliminar "${nombrePuesto}"?\n\nEsta acción eliminará también todas las máquinas asignadas y no se puede deshacer.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/puestos/${puestoId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            cargarPuestos();
            mostrarNotificacion('Puesto eliminado correctamente', 'success');
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al eliminar el puesto');
    }
}

// ================================
// GESTIÓN DE MÁQUINAS
// ================================

/**
 * Cargar lista de máquinas
 */
async function cargarMaquinas() {
    try {
        // Cargar puestos primero para el selector
        if (!dataPuestos) {
            await cargarPuestos();
        }
        
        const response = await fetch('/api/maquinas');
        const data = await response.json();
        
        if (data.success) {
            dataMaquinas = data.maquinas;
            mostrarListaMaquinas(data.maquinas);
            actualizarSelectorPuestos();
        } else {
            document.getElementById('lista-maquinas').innerHTML = '<p class="error">Error al cargar máquinas</p>';
        }
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('lista-maquinas').innerHTML = '<p class="error">Error de conexión</p>';
    }
}

/**
 * Mostrar lista de máquinas
 */
function mostrarListaMaquinas(maquinas) {
    const container = document.getElementById('lista-maquinas');
    
    if (maquinas.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚙️</div>
                <h4>No hay máquinas configuradas</h4>
                <p>Agrega máquinas a los puestos de trabajo para comenzar la asignación de terminales.</p>
                <button class="btn btn-primary" onclick="mostrarModalMaquina()">
                    ➕ Crear Primera Máquina
                </button>
            </div>
        `;
        return;
    }
    
    // Agrupar máquinas por puesto
    const maquinasPorPuesto = {};
    maquinas.forEach(maquina => {
        const puestoNombre = maquina.puesto_nombre || 'Sin asignar';
        if (!maquinasPorPuesto[puestoNombre]) {
            maquinasPorPuesto[puestoNombre] = [];
        }
        maquinasPorPuesto[puestoNombre].push(maquina);
    });
    
    container.innerHTML = Object.entries(maquinasPorPuesto).map(([puestoNombre, maquinasPuesto]) => `
        <div class="puesto-grupo">
            <h4 class="puesto-titulo">🏢 ${puestoNombre}</h4>
            <div class="maquinas-grid">
                ${maquinasPuesto.map(maquina => {
                    const tipo = maquina.tipo_operacion || 'MANUAL';
                    const tipoCls = tipo === 'AUTOMATICA' ? 'automatica' : tipo === 'SEMI-AUTOMATICA' ? 'semi' : 'manual';
                    const tipoIcon = tipo === 'AUTOMATICA' ? '🤖' : tipo === 'SEMI-AUTOMATICA' ? '⚡' : '🤚';
                    const regBadge = maquina.lleva_regulacion
                        ? `<span class="badge-reg">🔧 REG</span>` : '';
                    const pdfBtn = maquina.pdf_instrucciones
                        ? `<button class="btn-pdf" onclick="event.stopPropagation();verPdfMaquina('${maquina.id}')" title="Ver PDF">📄 PDF</button>`
                        : `<button class="btn-pdf sin-pdf" onclick="event.stopPropagation();editarMaquina('${maquina.id}')" title="Adjuntar PDF">📄 PDF</button>`;
                    return `
                    <div class="maquina-card tipo-${tipoCls}" data-id="${maquina.id}">
                        <div class="maquina-header">
                            <h5>${maquina.nombre}</h5>
                            <div class="maquina-actions">
                                <button class="btn-icon" onclick="editarMaquina('${maquina.id}')" title="Editar">✏️</button>
                                <button class="btn-icon" onclick="eliminarMaquina('${maquina.id}')" title="Eliminar">🗑️</button>
                            </div>
                        </div>
                        <p class="maquina-modelo">${maquina.modelo || 'Sin modelo'}</p>
                        <p class="maquina-descripcion">${maquina.descripcion || 'Sin descripción'}</p>
                        <div class="maquina-stats" style="gap:6px;flex-wrap:wrap;">
                            <span class="badge-tipo ${tipoCls}">${tipoIcon} ${tipo}</span>
                            ${regBadge}
                            ${pdfBtn}
                            <span class="stat">🔗 ${maquina.terminales_asignados ? maquina.terminales_asignados.length : 0}</span>
                            <span class="stat-status ${maquina.activo ? 'activo' : 'inactivo'}">
                                ${maquina.activo ? '✅ Activa' : '❌ Inactiva'}
                            </span>
                        </div>
                    </div>`;
                }).join('')}
            </div>
        </div>
    `).join('');
}

/**
 * Actualizar selector de puestos en el modal
 */
function actualizarSelectorPuestos() {
    const selector = document.getElementById('maquina-puesto');
    selector.innerHTML = '<option value="">Selecciona un puesto...</option>';
    
    if (dataPuestos && dataPuestos.length > 0) {
        dataPuestos.forEach(puesto => {
            if (puesto.activo) {
                selector.innerHTML += `<option value="${puesto.id}">${puesto.nombre}</option>`;
            }
        });
    }
}

/**
 * Mostrar modal para crear/editar máquina
 */
function mostrarModalMaquina(maquinaId = null) {
    const modal = document.getElementById('modal-maquina');
    const titulo = modal.querySelector('h3');
    
    console.log('Abriendo modal para máquina:', maquinaId);
    console.log('Datos de máquinas disponibles:', dataMaquinas);
    
    // Actualizar selector de puestos
    actualizarSelectorPuestos();
    
    if (maquinaId) {
        titulo.textContent = 'Editar Máquina';
        const maquina = dataMaquinas ? dataMaquinas.find(m => m.id === maquinaId) : null;
        console.log('Máquina encontrada para edición:', maquina);
        
        if (maquina) {
            // Esperar un poco para que el selector se actualice
            setTimeout(() => {
                document.getElementById('maquina-puesto').value = maquina.puesto_id || '';
                document.getElementById('maquina-nombre').value = maquina.nombre || '';
                document.getElementById('maquina-modelo').value = maquina.modelo || '';
                document.getElementById('maquina-descripcion').value = maquina.descripcion || '';

                // Tipo de operación
                const tipo = maquina.tipo_operacion || 'MANUAL';
                const radioEl = document.querySelector(`input[name="maquina-tipo"][value="${tipo}"]`);
                if (radioEl) radioEl.checked = true;

                // PDF existente
                _pdfPendiente = null;
                _pdfMaquinaIdActual = maquina.id;
                if (maquina.pdf_instrucciones) {
                    document.getElementById('pdf-drop-area').style.display = 'none';
                    document.getElementById('pdf-existente-nombre').textContent = maquina.pdf_instrucciones;
                    document.getElementById('pdf-existente-bar').style.display = 'flex';
                    document.getElementById('pdf-info-bar').style.display = 'none';
                } else {
                    document.getElementById('pdf-drop-area').style.display = '';
                    document.getElementById('pdf-existente-bar').style.display = 'none';
                    document.getElementById('pdf-info-bar').style.display = 'none';
                    document.getElementById('pdf-drop-area').classList.remove('tiene-pdf');
                    document.getElementById('pdf-drop-area').textContent = '📄 Clic para adjuntar PDF de instrucciones';
                }

                // Regulación
                const llevaReg = !!maquina.lleva_regulacion;
                document.getElementById('maquina-lleva-regulacion').checked = llevaReg;
                document.getElementById('pdf-reg-group').style.display = llevaReg ? '' : 'none';
                _pdfRegPendiente = null;
                if (llevaReg && maquina.pdf_regulacion) {
                    document.getElementById('pdf-reg-drop-area').style.display = 'none';
                    document.getElementById('pdf-reg-existente-nombre').textContent = maquina.pdf_regulacion;
                    document.getElementById('pdf-reg-existente-bar').style.display = 'flex';
                    document.getElementById('pdf-reg-info-bar').style.display = 'none';
                } else {
                    document.getElementById('pdf-reg-drop-area').style.display = '';
                    document.getElementById('pdf-reg-existente-bar').style.display = 'none';
                    document.getElementById('pdf-reg-info-bar').style.display = 'none';
                    document.getElementById('pdf-reg-drop-area').textContent = '🔧 Clic para adjuntar PDF de regulación';
                }
            }, 100);
        } else {
            console.error('Máquina no encontrada con ID:', maquinaId);
        }
    } else {
        titulo.textContent = 'Nueva Máquina';
        document.getElementById('maquina-puesto').value = '';
        document.getElementById('maquina-nombre').value = '';
        document.getElementById('maquina-modelo').value = '';
        document.getElementById('maquina-descripcion').value = '';
        // Reset tipo
        const radioManual = document.querySelector('input[name="maquina-tipo"][value="MANUAL"]');
        if (radioManual) radioManual.checked = true;
        // Reset PDF
        _pdfPendiente = null;
        _pdfMaquinaIdActual = null;
        document.getElementById('pdf-drop-area').style.display = '';
        document.getElementById('pdf-drop-area').classList.remove('tiene-pdf');
        document.getElementById('pdf-drop-area').textContent = '📄 Clic para adjuntar PDF de instrucciones';
        document.getElementById('pdf-info-bar').style.display = 'none';
        document.getElementById('pdf-existente-bar').style.display = 'none';
        // Reset regulación
        document.getElementById('maquina-lleva-regulacion').checked = false;
        document.getElementById('pdf-reg-group').style.display = 'none';
        _pdfRegPendiente = null;
        document.getElementById('pdf-reg-drop-area').style.display = '';
        document.getElementById('pdf-reg-drop-area').textContent = '🔧 Clic para adjuntar PDF de regulación';
        document.getElementById('pdf-reg-info-bar').style.display = 'none';
        document.getElementById('pdf-reg-existente-bar').style.display = 'none';
    }
    
    modal.dataset.editId = maquinaId || '';
    modal.classList.add('active');
}

/**
 * Guardar máquina
 */
async function guardarMaquina() {
    const puestoId = document.getElementById('maquina-puesto').value;
    const nombre = document.getElementById('maquina-nombre').value.trim();
    const modelo = document.getElementById('maquina-modelo').value.trim();
    const descripcion = document.getElementById('maquina-descripcion').value.trim();
    const editId = document.getElementById('modal-maquina').dataset.editId;
    const tipoRadio = document.querySelector('input[name="maquina-tipo"]:checked');
    const tipoOperacion = tipoRadio ? tipoRadio.value : 'MANUAL';
    const llevaRegulacion = document.getElementById('maquina-lleva-regulacion').checked;
    
    if (!puestoId) {
        alert('Debe seleccionar un puesto de trabajo');
        return;
    }
    
    if (!nombre) {
        alert('El nombre de la máquina es obligatorio');
        return;
    }
    
    try {
        const url = editId ? `/api/maquinas/${editId}` : '/api/maquinas';
        const method = editId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                puesto_id: puestoId,
                nombre: nombre,
                modelo: modelo || '',
                descripcion: descripcion || '',
                tipo_operacion: tipoOperacion,
                lleva_regulacion: llevaRegulacion
            })
        });
        
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        
        if (!data.success) {
            alert('Error del servidor: ' + (data.message || 'Error desconocido'));
            return;
        }

        const maquinaId = editId || data.maquina.id;

        // Subir PDF pendiente si lo hay
        if (_pdfPendiente) {
            const formData = new FormData();
            formData.append('pdf', _pdfPendiente);
            const pdfResp = await fetch(`/api/maquinas/${maquinaId}/pdf`, {
                method: 'POST',
                body: formData
            });
            const pdfData = await pdfResp.json();
            if (!pdfData.success) {
                alert('Máquina guardada pero error al subir PDF instrucciones: ' + pdfData.message);
            }
        }

        // Subir PDF de regulación pendiente si lo hay
        if (_pdfRegPendiente) {
            const formData = new FormData();
            formData.append('pdf', _pdfRegPendiente);
            const pdfResp = await fetch(`/api/maquinas/${maquinaId}/pdf-regulacion`, {
                method: 'POST',
                body: formData
            });
            const pdfData = await pdfResp.json();
            if (!pdfData.success) {
                alert('Máquina guardada pero error al subir PDF regulación: ' + pdfData.message);
            }
        }

        cerrarModal('modal-maquina');
        cargarMaquinas();
        mostrarNotificacion(editId ? 'Máquina actualizada correctamente' : 'Máquina creada correctamente', 'success');

    } catch (error) {
        console.error('Error completo:', error);
        alert('Error al guardar la máquina: ' + error.message);
    }
}

/**
 * Editar máquina
 */
function editarMaquina(maquinaId) {
    mostrarModalMaquina(maquinaId);
}

/**
 * Eliminar máquina
 */
async function eliminarMaquina(maquinaId) {
    const maquina = dataMaquinas.find(m => m.id === maquinaId);
    const nombreMaquina = maquina ? maquina.nombre : 'esta máquina';
    
    if (!confirm(`¿Estás seguro de que quieres eliminar "${nombreMaquina}"?\n\nEsta acción eliminará también todas las asignaciones de terminales y no se puede deshacer.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/maquinas/${maquinaId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            cargarMaquinas();
            mostrarNotificacion('Máquina eliminada correctamente', 'success');
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al eliminar la máquina');
    }
}

/**
 * Cargar asignaciones de terminales
 */
async function cargarAsignaciones() {
    try {
        // Cargar terminales disponibles
        const responseTerminales = await fetch('/api/terminales-disponibles');
        const dataTerminales = await responseTerminales.json();
        
        // Cargar máquinas para el selector
        const responseMaquinas = await fetch('/api/maquinas');
        const dataMaquinas = await responseMaquinas.json();
        
        if (dataTerminales.success && dataMaquinas.success) {
            mostrarAsignaciones(dataTerminales, dataMaquinas.maquinas);
        } else {
            document.getElementById('lista-asignaciones').innerHTML = '<p class="error">Error al cargar datos</p>';
        }
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('lista-asignaciones').innerHTML = '<p class="error">Error de conexión</p>';
    }
}

/**
 * Mostrar lista de asignaciones — vista lista agrupada por puesto
 */
function mostrarAsignaciones(dataTerminales, maquinas) {
    // Actualizar estadísticas
    document.getElementById('total-terminales').textContent = `${dataTerminales.total} terminales`;
    document.getElementById('sin-asignar').textContent = `${dataTerminales.sin_asignar} sin asignar`;

    const alertElement = document.getElementById('sin-asignar');
    if (dataTerminales.sin_asignar > 0) {
        alertElement.classList.add('alert');
    } else {
        alertElement.classList.remove('alert');
    }

    const container = document.getElementById('lista-asignaciones');

    if (dataTerminales.terminales.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📊</div>
                <h4>No hay terminales cargados</h4>
                <p>Sube archivos Excel con datos de cableado para ver los terminales disponibles.</p>
            </div>
        `;
        return;
    }

    // Selector de máquinas para asignación rápida
    const selectorMaquinas = maquinas.map(m =>
        `<option value="${m.id}">${m.puesto_nombre} — ${m.nombre}</option>`
    ).join('');

    // Mapa de máquina → tipo (para badges en filas)
    const tipoMapa = {};
    maquinas.forEach(m => { tipoMapa[m.id] = m.tipo_operacion || 'MANUAL'; });

    // ── Calcular estadísticas por tipo de operación ──────────────────
    const statsTotal = { MANUAL: 0, AUTOMATICA: 0, 'SEMI-AUTOMATICA': 0, sinAsignar: 0 };
    dataTerminales.terminales.forEach(t => {
        if (!t.asignado) { statsTotal.sinAsignar++; }
        else {
            const tipo = tipoMapa[t.asignacion.maquina_id] || 'MANUAL';
            statsTotal[tipo] = (statsTotal[tipo] || 0) + 1;
        }
    });
    const totalAsignados = statsTotal.MANUAL + statsTotal.AUTOMATICA + statsTotal['SEMI-AUTOMATICA'];
    const pct = n => totalAsignados ? Math.round(n * 100 / totalAsignados) : 0;

    const statsHTML = `
        <div class="stats-tipo-bar">
            <div class="stats-tipo-title">Distribución por tipo de operación</div>
            <div class="stats-tipo-pills">
                <div class="stp stp-manual">
                    <span class="stp-icon">🤚</span>
                    <span class="stp-label">Manual</span>
                    <span class="stp-val">${statsTotal.MANUAL}</span>
                    <span class="stp-pct">${pct(statsTotal.MANUAL)}%</span>
                </div>
                <div class="stp stp-semi">
                    <span class="stp-icon">⚡</span>
                    <span class="stp-label">Semi-Auto</span>
                    <span class="stp-val">${statsTotal['SEMI-AUTOMATICA']}</span>
                    <span class="stp-pct">${pct(statsTotal['SEMI-AUTOMATICA'])}%</span>
                </div>
                <div class="stp stp-auto">
                    <span class="stp-icon">🤖</span>
                    <span class="stp-label">Automática</span>
                    <span class="stp-val">${statsTotal.AUTOMATICA}</span>
                    <span class="stp-pct">${pct(statsTotal.AUTOMATICA)}%</span>
                </div>
                ${statsTotal.sinAsignar > 0 ? `<div class="stp stp-none">
                    <span class="stp-icon">⚠️</span>
                    <span class="stp-label">Sin asignar</span>
                    <span class="stp-val">${statsTotal.sinAsignar}</span>
                    <span class="stp-pct"></span>
                </div>` : ''}
            </div>
            <div class="stats-tipo-barra">
                ${statsTotal.MANUAL    > 0 ? `<div class="stb-seg manual"    style="width:${pct(statsTotal.MANUAL)}%"    title="Manual ${pct(statsTotal.MANUAL)}%"></div>` : ''}
                ${statsTotal['SEMI-AUTOMATICA'] > 0 ? `<div class="stb-seg semi" style="width:${pct(statsTotal['SEMI-AUTOMATICA'])}%" title="Semi-Auto ${pct(statsTotal['SEMI-AUTOMATICA'])}%"></div>` : ''}
                ${statsTotal.AUTOMATICA > 0 ? `<div class="stb-seg auto"    style="width:${pct(statsTotal.AUTOMATICA)}%" title="Automática ${pct(statsTotal.AUTOMATICA)}%"></div>` : ''}
            </div>
        </div>`;

    // Agrupar terminales: asignados por puesto, después sin asignar
    const grupos = {};
    const sinAsignarList = [];

    dataTerminales.terminales.forEach(t => {
        if (t.asignado) {
            const key = t.asignacion.puesto_nombre;
            if (!grupos[key]) grupos[key] = [];
            grupos[key].push(t);
        } else {
            sinAsignarList.push(t);
        }
    });

    // Generar HTML de grupos asignados
    const gruposHTML = Object.entries(grupos).map(([puestoNombre, lista]) => `
        <div class="tl-group" data-grupo="${puestoNombre}">
            <div class="tl-group-header" onclick="toggleGrupo(this.parentElement)">
                <span class="tl-group-stripe asignado"></span>
                <span class="tl-group-name">${puestoNombre}</span>
                <span class="tl-group-count">${lista.length} terminal${lista.length !== 1 ? 'es' : ''}</span>
                <span class="tl-group-arrow">▼</span>
            </div>
            <div class="tl-rows">
                ${lista.map(t => {
                    const mTipo = t.asignacion ? tipoMapa[t.asignacion.maquina_id] || 'MANUAL' : 'MANUAL';
                    const mTipoCls = mTipo === 'AUTOMATICA' ? 'automatica' : mTipo === 'SEMI-AUTOMATICA' ? 'semi' : 'manual';
                    const mTipoIcon = mTipo === 'AUTOMATICA' ? '🤖' : mTipo === 'SEMI-AUTOMATICA' ? '⚡' : '🤚';
                    return `
                    <div class="terminal-row asignado"
                         data-terminal="${t.terminal}"
                         data-estado="asignados">
                        <span class="tr-check-spacer"></span>
                        ${imgThumb(t)}
                        <span class="tr-dot asignado"></span>
                        <span class="tr-code">${t.terminal}</span>
                        <span class="tr-assign asignado">${t.asignacion.puesto_nombre} · ${t.asignacion.maquina_nombre}</span>
                        <span class="badge-tipo ${mTipoCls}" style="font-size:0.62rem;padding:1px 6px;">${mTipoIcon} ${mTipo}</span>
                        ${gavetaChip(t)}
                        <span class="tr-badge asignado">Asignado</span>
                        <button class="btn-desvincular" onclick="desasignarTerminal('${t.terminal}')" title="Desasignar">✕</button>
                    </div>`; }).join('')}
            </div>
        </div>
    `).join('');

    // Grupo sin asignar
    const sinAsignarHTML = sinAsignarList.length > 0 ? `
        <div class="tl-group" data-grupo="sin-asignar">
            <div class="tl-group-header" onclick="toggleGrupo(this.parentElement)">
                <span class="tl-group-stripe sin-asignar"></span>
                <span class="tl-group-name">SIN ASIGNAR</span>
                <span class="tl-group-count">${sinAsignarList.length} terminal${sinAsignarList.length !== 1 ? 'es' : ''}</span>
                <span class="tl-group-arrow">▼</span>
            </div>
            <div class="tl-rows">
                ${sinAsignarList.map(t => `
                    <div class="terminal-row sin-asignar"
                         data-terminal="${t.terminal}"
                         data-estado="sin-asignar"
                         onclick="toggleSeleccionTerminal(this)">
                        <span class="tr-check"></span>
                        ${imgThumb(t)}
                        <span class="tr-dot sin-asignar"></span>
                        <span class="tr-code">${t.terminal}</span>
                        <span class="tr-assign sin-asignar">sin asignar</span>
                        ${gavetaChip(t)}
                        <span class="tr-badge sin-asignar">Pendiente</span>
                    </div>
                `).join('')}
            </div>
        </div>
    ` : '';

    container.innerHTML = `
        ${statsHTML}
        <div class="asignacion-rapida">
            <h4>Asignación Rápida</h4>
            <div class="asignacion-controles">
                <select id="maquina-destino">
                    <option value="">Selecciona una máquina...</option>
                    ${selectorMaquinas}
                </select>
                <button class="btn btn-primary" onclick="asignarSeleccionados()">
                    Asignar Seleccionados
                </button>
            </div>
        </div>
        <div class="terminales-list" id="terminales-grid">
            ${gruposHTML}
            ${sinAsignarHTML}
        </div>
    `;

    aplicarFiltros();
}

/**
 * Aplicar filtros de visualización
 */
function aplicarFiltros() {
    const filtroEstado = document.getElementById('filtro-estado').value;
    const busqueda = document.getElementById('buscar-terminal').value.toLowerCase().trim();

    // Mostrar/ocultar grupos según filtro de estado
    document.querySelectorAll('.tl-group').forEach(grupo => {
        const essinAsignar = grupo.dataset.grupo === 'sin-asignar';
        let mostrarGrupo = true;

        if (filtroEstado === 'asignados' && essinAsignar) mostrarGrupo = false;
        if (filtroEstado === 'sin-asignar' && !essinAsignar) mostrarGrupo = false;

        grupo.style.display = mostrarGrupo ? '' : 'none';
    });

    // Filtrar filas individuales por búsqueda
    document.querySelectorAll('.terminal-row').forEach(row => {
        const codigo = row.dataset.terminal ? row.dataset.terminal.toLowerCase() : '';
        const estadoRow = row.dataset.estado;
        let visible = true;

        if (filtroEstado === 'asignados' && estadoRow === 'sin-asignar') visible = false;
        if (filtroEstado === 'sin-asignar' && estadoRow !== 'sin-asignar') visible = false;
        if (busqueda && !codigo.includes(busqueda)) visible = false;

        row.style.display = visible ? '' : 'none';
    });

    // Ocultar grupos que tienen todas sus filas ocultas (por búsqueda)
    if (busqueda) {
        document.querySelectorAll('.tl-group').forEach(grupo => {
            const filas = grupo.querySelectorAll('.terminal-row');
            const hayVisibles = Array.from(filas).some(r => r.style.display !== 'none');
            grupo.style.display = hayVisibles ? '' : 'none';
        });
    }
}

/**
 * Colapsar/expandir un grupo
 */
function toggleGrupo(grupoEl) {
    grupoEl.classList.toggle('collapsed');
}

/**
 * Asignar terminales seleccionados
 */
async function asignarSeleccionados() {
    const maquinaId = document.getElementById('maquina-destino').value;
    if (!maquinaId) {
        alert('Selecciona una máquina de destino');
        return;
    }
    
    const seleccionadas = document.querySelectorAll('.terminal-row.seleccionado');
    if (seleccionadas.length === 0) {
        alert('Pulsa sobre las tarjetas de terminal que quieras asignar');
        return;
    }
    
    const terminales = Array.from(seleccionadas).map(card => card.dataset.terminal);
    
    try {
        for (const terminal of terminales) {
            await fetch('/api/asignar-terminal', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ terminal, maquina_id: maquinaId })
            });
        }
        
        mostrarNotificacion(`${terminales.length} terminales asignados correctamente`, 'success');
        cargarAsignaciones();
        
    } catch (error) {
        console.error('Error:', error);
        alert('Error al asignar terminales');
    }
}

/**
 * Desasignar terminal
 */
async function desasignarTerminal(terminal) {
    if (!confirm(`¿Estás seguro de desasignar el terminal ${terminal}?`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/desasignar-terminal', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ terminal })
        });
        
        const data = await response.json();
        
        if (data.success) {
            mostrarNotificacion(data.message, 'success');
            cargarAsignaciones();
        } else {
            alert('Error: ' + data.message);
        }
        
    } catch (error) {
        console.error('Error:', error);
        alert('Error al desasignar terminal');
    }
}

/**
 * Mostrar asignación rápida para un terminal específico
 */
function mostrarAsignacionRapida(terminal) {
    const row = document.querySelector(`.terminal-row[data-terminal="${terminal}"]`);
    if (row) toggleSeleccionTerminal(row);
    const dest = document.getElementById('maquina-destino');
    if (dest) dest.focus();
}

function toggleSeleccionTerminal(row) {
    row.classList.toggle('seleccionado');
}

// ================================
// IMÁGENES DE TERMINALES
// ================================

/** Genera el HTML del thumbnail o placeholder para una fila */
function imgThumb(t) {
    const cod = t.terminal;
    if (t.imagen_data) {
        return `<span class="tr-img-wrap" onclick="event.stopPropagation();abrirModalImagen('${cod}')" title="Ver/editar imagen">
                    <img class="tr-img" src="${t.imagen_data}" alt="${cod}">
                </span>`;
    }
    return `<span class="tr-img-placeholder" onclick="event.stopPropagation();abrirModalImagen('${cod}')" title="Añadir imagen">📷</span>`;
}

/** Genera el chip de gaveta para una fila */
function gavetaChip(t) {
    const cod = t.terminal;
    if (t.gaveta) {
        return `<span class="tr-gaveta" data-gaveta="${t.gaveta}" onclick="event.stopPropagation();editarGaveta('${cod}',this)" title="Gaveta: ${t.gaveta} — clic para editar">📦 ${t.gaveta}</span>`;
    }
    return `<span class="tr-gaveta empty" onclick="event.stopPropagation();editarGaveta('${cod}',this)" title="Asignar gaveta">📦 gaveta</span>`;
}

let _imgTerminalActual = null;   // código del terminal en edición
let _imgNuevoDataUrl   = null;   // data URL pendiente de guardar

/** Abre el modal de imagen para un terminal */
function abrirModalImagen(codigo) {
    _imgTerminalActual = codigo;
    _imgNuevoDataUrl   = null;

    document.getElementById('modal-img-titulo').textContent = `Imagen · ${codigo}`;
    document.getElementById('img-file-input').value = '';
    document.getElementById('img-btn-save').disabled = true;

    // Buscar imagen actual en el DOM (thumbnail ya renderizado)
    const row = document.querySelector(`.terminal-row[data-terminal="${codigo}"]`);
    const imgEl = row ? row.querySelector('.tr-img') : null;
    const box   = document.getElementById('img-preview-box');
    const btnDel = document.getElementById('img-btn-delete');

    if (imgEl) {
        box.innerHTML = `<img src="${imgEl.src}" alt="${codigo}">`;
        btnDel.style.display = '';
    } else {
        box.innerHTML = `<span class="img-preview-empty">📷</span>`;
        btnDel.style.display = 'none';
    }

    document.getElementById('modal-img-terminal').classList.add('active');
}

/** Cuando el usuario selecciona un archivo */
function imgOnFileSelected(input) {
    const file = input.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        const img = new Image();
        img.onload = function() {
            // Resize manteniendo proporción, lado máximo 600 px, JPEG 85 %
            const MAX = 600;
            let w = img.width, h = img.height;
            if (w >= h) { if (w > MAX) { h = Math.round(h * MAX / w); w = MAX; } }
            else         { if (h > MAX) { w = Math.round(w * MAX / h); h = MAX; } }

            const canvas = document.createElement('canvas');
            canvas.width  = w;
            canvas.height = h;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, w, h);

            const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
            const kb = Math.round(dataUrl.length * 0.75 / 1024);

            if (kb > 300) {
                alert(`La imagen comprimida pesa ${kb} KB (máx 300 KB).\nPor favor usa una imagen más pequeña.`);
                return;
            }

            _imgNuevoDataUrl = dataUrl;
            document.getElementById('img-preview-box').innerHTML = `<img src="${dataUrl}" alt="preview">`;
            document.getElementById('img-btn-save').disabled = false;
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

/** Guarda la imagen en la API */
async function imgGuardar() {
    if (!_imgNuevoDataUrl || !_imgTerminalActual) return;
    try {
        const resp = await fetch(`/api/terminal-imagen/${encodeURIComponent(_imgTerminalActual)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ imagen_data: _imgNuevoDataUrl })
        });
        const data = await resp.json();
        if (data.success) {
            cerrarModal('modal-img-terminal');
            cargarAsignaciones();   // refresca para mostrar el nuevo thumbnail
        } else {
            alert('Error: ' + data.message);
        }
    } catch (e) {
        alert('Error de conexión al guardar la imagen');
    }
}

/** Elimina la imagen del terminal */
async function imgEliminar() {
    if (!_imgTerminalActual) return;
    if (!confirm(`¿Eliminar la imagen del terminal ${_imgTerminalActual}?`)) return;
    try {
        const resp = await fetch(`/api/terminal-imagen/${encodeURIComponent(_imgTerminalActual)}`, {
            method: 'DELETE'
        });
        const data = await resp.json();
        if (data.success) {
            cerrarModal('modal-img-terminal');
            cargarAsignaciones();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (e) {
        alert('Error de conexión al eliminar la imagen');
    }
}

// ================================
// ANÁLISIS POR CORTE DE CABLE
// ================================

let _analisisData = null;

async function cargarAnalisis() {
    const container = document.getElementById('lista-analisis');
    const globalEl  = document.getElementById('analisis-global');
    container.innerHTML = '<div class="loading">🔄 Calculando estadísticas...</div>';
    globalEl.style.display = 'none';
    try {
        const resp = await fetch('/api/estadisticas-tipo-operacion');
        const data = await resp.json();
        if (!data.success) {
            container.innerHTML = '<p class="error">Error al cargar estadísticas</p>';
            return;
        }
        _analisisData = data;
        renderAnalisis(data);
    } catch (e) {
        container.innerHTML = '<p class="error">Error de conexión</p>';
    }
}

function ordenarAnalisis() {
    if (_analisisData) renderAnalisis(_analisisData);
}

function renderAnalisis(data) {
    const container = document.getElementById('lista-analisis');
    const globalEl  = document.getElementById('analisis-global');
    const orden     = document.getElementById('analisis-orden')?.value || 'nombre';

    if (!data.por_archivo || data.por_archivo.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📊</div>
                <h4>Sin datos</h4>
                <p>No hay archivos de corte activos o no tienen terminales.</p>
            </div>`;
        return;
    }

    // ── Bloque global ──────────────────────────────────────────────
    const g = data.global;
    const totalAsig = g.MANUAL + g.AUTOMATICA + (g['SEMI-AUTOMATICA'] || 0);
    const gPct = n => totalAsig ? Math.round(n * 100 / totalAsig) : 0;

    globalEl.style.display = '';
    globalEl.innerHTML = `
        <div class="analisis-global-row">
            <div><span class="ag-label">TOTAL TERMINALES</span><br><span class="ag-val">${g.total}</span></div>
            <div class="analisis-global-sep"></div>
            <div><span class="ag-label">🤚 Manual</span><br><span class="ag-val">${g.MANUAL}</span> <span class="ag-pct">${gPct(g.MANUAL)}%</span></div>
            <div class="analisis-global-sep"></div>
            <div><span class="ag-label">⚡ Semi-Auto</span><br><span class="ag-val">${g['SEMI-AUTOMATICA']||0}</span> <span class="ag-pct">${gPct(g['SEMI-AUTOMATICA']||0)}%</span></div>
            <div class="analisis-global-sep"></div>
            <div><span class="ag-label">🤖 Automática</span><br><span class="ag-val">${g.AUTOMATICA}</span> <span class="ag-pct">${gPct(g.AUTOMATICA)}%</span></div>
            <div class="analisis-global-sep"></div>
            <div><span class="ag-label" style="color:#fcd34d;">⚠️ Sin asignar</span><br><span class="ag-val" style="color:#fcd34d;">${g.sin_asignar}</span></div>
        </div>
        <div style="padding:0 16px 14px;">
            <div class="analisis-barra" style="height:8px;">
                ${g.MANUAL      > 0 ? `<div class="stb-seg manual" style="width:${gPct(g.MANUAL)}%"></div>` : ''}
                ${(g['SEMI-AUTOMATICA']||0) > 0 ? `<div class="stb-seg semi" style="width:${gPct(g['SEMI-AUTOMATICA']||0)}%"></div>` : ''}
                ${g.AUTOMATICA  > 0 ? `<div class="stb-seg auto"   style="width:${gPct(g.AUTOMATICA)}%"></div>` : ''}
            </div>
        </div>`;

    // ── Ordenar ────────────────────────────────────────────────────
    const lista = [...data.por_archivo];
    const pct = (n, total) => total ? Math.round(n * 100 / total) : 0;
    lista.sort((a, b) => {
        const totA = a.manual + a.semi + a.automatica || 1;
        const totB = b.manual + b.semi + b.automatica || 1;
        switch (orden) {
            case 'total':      return b.total - a.total;
            case 'manual_pct': return pct(b.manual, totB) - pct(a.manual, totA);
            case 'auto_pct':   return pct(b.automatica, totB) - pct(a.automatica, totA);
            case 'semi_pct':   return pct(b.semi, totB) - pct(a.semi, totA);
            case 'sin_pct':    return pct(b.sin_asignar, b.total) - pct(a.sin_asignar, a.total);
            default:           return a.nombre.localeCompare(b.nombre);
        }
    });

    // ── Render cards ───────────────────────────────────────────────
    container.innerHTML = `<div class="analisis-grid">${lista.map(item => {
        const tot   = item.total || 1;
        const asig  = item.manual + item.semi + item.automatica || 1;
        const wM    = pct(item.manual,     tot);
        const wS    = pct(item.semi,       tot);
        const wA    = pct(item.automatica, tot);
        const wN    = pct(item.sin_asignar, tot);
        const pM    = pct(item.manual,     asig);
        const pS    = pct(item.semi,       asig);
        const pA    = pct(item.automatica, asig);

        // Nombre corto: quitar fecha tipo _YYYYMMDD o _vX al final
        const nombreCorto = item.nombre.replace(/_\d{8}(_v\d+)?$/i, '').replace(/_v\d+$/i, '');

        return `
        <div class="analisis-card">
            <div class="analisis-card-header">
                <span class="analisis-card-nombre" title="${item.archivo}">${nombreCorto}</span>
                <span class="analisis-card-total">${item.total} terminales</span>
            </div>
            <div class="analisis-barra">
                ${wM > 0 ? `<div class="stb-seg manual" style="width:${wM}%" title="Manual ${wM}%"></div>` : ''}
                ${wS > 0 ? `<div class="stb-seg semi"   style="width:${wS}%" title="Semi-Auto ${wS}%"></div>` : ''}
                ${wA > 0 ? `<div class="stb-seg auto"   style="width:${wA}%" title="Automática ${wA}%"></div>` : ''}
                ${wN > 0 ? `<div class="stb-seg" style="width:${wN}%;background:rgba(100,116,139,.5);" title="Sin asignar ${wN}%"></div>` : ''}
            </div>
            <div class="analisis-pills">
                ${item.manual > 0      ? `<div class="analisis-pill manual"><span>🤚</span><span class="ap-val">${item.manual}</span><span class="ap-pct">${pM}%</span></div>` : ''}
                ${item.semi > 0        ? `<div class="analisis-pill semi"><span>⚡</span><span class="ap-val">${item.semi}</span><span class="ap-pct">${pS}%</span></div>` : ''}
                ${item.automatica > 0  ? `<div class="analisis-pill auto"><span>🤖</span><span class="ap-val">${item.automatica}</span><span class="ap-pct">${pA}%</span></div>` : ''}
                ${item.sin_asignar > 0 ? `<div class="analisis-pill none"><span>⚠️</span><span class="ap-val">${item.sin_asignar}</span><span class="ap-pct">${wN}%</span></div>` : ''}
            </div>
        </div>`;
    }).join('')}</div>`;
}

// ================================
// PDF DE MÁQUINAS
// ================================

/** Cuando el usuario selecciona un PDF desde el input */
function pdfOnFileSelected(input) {
    const file = input.files[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        alert('Solo se aceptan archivos PDF.');
        return;
    }
    _pdfPendiente = file;
    document.getElementById('pdf-drop-area').style.display = 'none';
    document.getElementById('pdf-nombre-display').textContent = file.name;
    document.getElementById('pdf-info-bar').style.display = 'flex';
}

/** Quitar PDF pendiente (aún no subido) */
function pdfEliminarPendiente() {
    _pdfPendiente = null;
    document.getElementById('pdf-file-input').value = '';
    document.getElementById('pdf-info-bar').style.display = 'none';
    document.getElementById('pdf-drop-area').style.display = '';
    document.getElementById('pdf-drop-area').classList.remove('tiene-pdf');
    document.getElementById('pdf-drop-area').textContent = '📄 Clic para adjuntar PDF de instrucciones';
}

/** Ver el PDF ya guardado en el servidor */
function pdfVerExistente() {
    if (!_pdfMaquinaIdActual) return;
    window.open(`/api/maquinas/${_pdfMaquinaIdActual}/pdf`, '_blank');
}

/** Eliminar el PDF ya guardado en el servidor */
async function pdfEliminarExistente() {
    if (!_pdfMaquinaIdActual) return;
    if (!confirm('¿Eliminar el PDF de instrucciones de esta máquina?')) return;
    try {
        const resp = await fetch(`/api/maquinas/${_pdfMaquinaIdActual}/pdf`, { method: 'DELETE' });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('pdf-existente-bar').style.display = 'none';
            document.getElementById('pdf-drop-area').style.display = '';
            document.getElementById('pdf-drop-area').classList.remove('tiene-pdf');
            document.getElementById('pdf-drop-area').textContent = '📄 Clic para adjuntar PDF de instrucciones';
            mostrarNotificacion('PDF eliminado correctamente', 'success');
            cargarMaquinas();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (e) {
        alert('Error de conexión al eliminar el PDF');
    }
}

/** Abrir el PDF de una máquina desde la card */
function verPdfMaquina(maquinaId) {
    window.open(`/api/maquinas/${maquinaId}/pdf`, '_blank');
}

// ── PDF Regulación ─────────────────────────────────────────────────

/** Mostrar/ocultar sección PDF regulación según el toggle */
function toggleRegulacion(checked) {
    document.getElementById('pdf-reg-group').style.display = checked ? '' : 'none';
}

function pdfRegOnFileSelected(input) {
    const file = input.files[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        alert('Solo se aceptan archivos PDF.');
        return;
    }
    _pdfRegPendiente = file;
    document.getElementById('pdf-reg-drop-area').style.display = 'none';
    document.getElementById('pdf-reg-nombre-display').textContent = file.name;
    document.getElementById('pdf-reg-info-bar').style.display = 'flex';
}

function pdfRegEliminarPendiente() {
    _pdfRegPendiente = null;
    document.getElementById('pdf-reg-file-input').value = '';
    document.getElementById('pdf-reg-info-bar').style.display = 'none';
    document.getElementById('pdf-reg-drop-area').style.display = '';
    document.getElementById('pdf-reg-drop-area').textContent = '🔧 Clic para adjuntar PDF de regulación';
}

function pdfRegVerExistente() {
    if (!_pdfMaquinaIdActual) return;
    window.open(`/api/maquinas/${_pdfMaquinaIdActual}/pdf-regulacion`, '_blank');
}

async function pdfRegEliminarExistente() {
    if (!_pdfMaquinaIdActual) return;
    if (!confirm('¿Eliminar el PDF de regulación de esta máquina?')) return;
    try {
        const resp = await fetch(`/api/maquinas/${_pdfMaquinaIdActual}/pdf-regulacion`, { method: 'DELETE' });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('pdf-reg-existente-bar').style.display = 'none';
            document.getElementById('pdf-reg-drop-area').style.display = '';
            document.getElementById('pdf-reg-drop-area').textContent = '🔧 Clic para adjuntar PDF de regulación';
            mostrarNotificacion('PDF de regulación eliminado', 'success');
            cargarMaquinas();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (e) {
        alert('Error de conexión al eliminar el PDF de regulación');
    }
}

// ================================
// GAVETAS DE TERMINALES
// ================================

/**
 * Activa el modo edición inline del chip de gaveta
 */
function editarGaveta(codigo, chipEl) {
    // Evitar doble apertura
    if (chipEl.querySelector('input')) return;

    const valorActual = chipEl.dataset.gaveta || '';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'tr-gaveta-input';
    input.value = valorActual;
    input.placeholder = 'Ej: A-12 ó Bandeja 3';
    input.maxLength = 80;

    chipEl.replaceWith(input);
    input.focus();
    input.select();

    const confirmar = () => {
        const nuevo = input.value.trim();
        guardarGaveta(codigo, nuevo, input);
    };

    input.addEventListener('blur',    confirmar);
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter')  { e.preventDefault(); confirmar(); }
        if (e.key === 'Escape') {
            // Restaurar chip sin guardar
            input.replaceWith(_crearChipGaveta(codigo, valorActual));
        }
    });
}

/** Crea un chip de gaveta a partir de código y valor */
function _crearChipGaveta(codigo, gaveta) {
    const span = document.createElement('span');
    if (gaveta) {
        span.className = 'tr-gaveta';
        span.dataset.gaveta = gaveta;
        span.title = `Gaveta: ${gaveta} — clic para editar`;
        span.textContent = `📦 ${gaveta}`;
    } else {
        span.className = 'tr-gaveta empty';
        span.title = 'Asignar gaveta';
        span.textContent = '📦 gaveta';
    }
    span.addEventListener('click', e => { e.stopPropagation(); editarGaveta(codigo, span); });
    return span;
}

/** Llama a la API y actualiza el chip en el DOM */
async function guardarGaveta(codigo, gaveta, inputEl) {
    try {
        let resp, data;
        if (gaveta) {
            resp = await fetch(`/api/terminal-gaveta/${encodeURIComponent(codigo)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ gaveta })
            });
        } else {
            // Vacío = eliminar
            resp = await fetch(`/api/terminal-gaveta/${encodeURIComponent(codigo)}`, {
                method: 'DELETE'
            });
        }
        data = await resp.json();
        if (!data.success) { alert('Error: ' + data.message); }
    } catch (e) {
        console.error('Error al guardar gaveta', e);
    } finally {
        // Siempre restaurar el chip (con el valor nuevo o sin él)
        inputEl.replaceWith(_crearChipGaveta(codigo, gaveta));
    }
}

// ================================
// FUNCIONES AUXILIARES
// ================================

/**
 * Cerrar modal
 */
function cerrarModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

/**
 * Mostrar notificación
 */
function mostrarNotificacion(mensaje, tipo = 'info') {
    // Implementación simple con alert por ahora
    // En el futuro se puede mejorar con toast notifications
    alert(mensaje);
}

// ================================
// INICIALIZACIÓN
// ================================

// Inicializar al cargar la página
document.addEventListener('DOMContentLoaded', function() {
    // Cargar puestos por defecto
    cargarPuestos();
    
    // Event listeners para cerrar modales con escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.active').forEach(modal => {
                modal.classList.remove('active');
            });
        }
    });
    
    // Event listeners para cerrar modales haciendo clic fuera
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });
});

// ================================
// KANBAN DE STOCK
// ================================

let _kanbanData = null;

async function cargarKanban() {
    const container = document.getElementById('lista-kanban');
    container.classList.add('loading');
    container.textContent = '🔄 Cargando...';
    try {
        const resp = await fetch('/api/kanban-terminales');
        const data = await resp.json();
        if (!data.success) { container.innerHTML = '<p class="error">Error al cargar</p>'; return; }
        _kanbanData = data.terminales;
        document.getElementById('kanban-total').textContent = data.total + ' terminales';
        container.classList.remove('loading');
        renderKanban();
    } catch (e) {
        container.innerHTML = '<p class="error">Error de conexión</p>';
    }
}

function renderKanban() {
    if (!_kanbanData) return;
    const container   = document.getElementById('lista-kanban');
    const filtroStock = document.getElementById('kanban-filtro-stock').value;
    const buscar      = (document.getElementById('kanban-buscar').value || '').trim().toLowerCase();
    const agrupar     = document.getElementById('kanban-agrupar').value;

    let lista = _kanbanData.filter(t => {
        if (buscar && !t.terminal.toLowerCase().includes(buscar)) return false;
        if (filtroStock === 'bajo') return t.stock_actual <= t.stock_minimo;
        if (filtroStock === 'ok')   return t.stock_actual > t.stock_minimo;
        return true;
    });

    // Contar alertas en el total (sin filtro) para el badge
    const nBajo = _kanbanData.filter(t => t.stock_actual <= t.stock_minimo).length;
    const badgeEl = document.getElementById('kanban-stock-bajo');
    if (nBajo > 0) {
        badgeEl.textContent = '⚠ ' + nBajo + ' stock bajo';
        badgeEl.style.display = '';
    } else {
        badgeEl.style.display = 'none';
    }

    if (lista.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="empty-icon">📦</div><h4>Sin resultados</h4><p>No hay terminales que coincidan con los filtros.</p></div>';
        return;
    }

    if (agrupar === 'ninguno') {
        container.innerHTML = `<div class="kanban-grid">${lista.map(_tarjetaKanban).join('')}</div>`;
    } else {
        const key = agrupar === 'maquina' ? 'maquina_nombre' : 'puesto_nombre';
        const grupos = {};
        lista.forEach(t => {
            const g = t[key] || '— Sin asignar';
            if (!grupos[g]) grupos[g] = [];
            grupos[g].push(t);
        });
        container.innerHTML = Object.keys(grupos).sort().map(g => `
            <div style="margin-bottom:20px;">
                <div style="font-family:'Bebas Neue',sans-serif;font-size:16px;letter-spacing:.08em;
                            color:var(--text);border-bottom:1px solid var(--border);
                            padding-bottom:6px;margin-bottom:10px;">
                    <span style="display:inline-block;width:4px;height:14px;background:var(--accent);
                                 border-radius:2px;margin-right:8px;vertical-align:middle;"></span>
                    ${g} <span style="font-family:'DM Mono',monospace;font-size:11px;color:var(--text-muted);font-weight:normal;">(${grupos[g].length})</span>
                </div>
                <div class="kanban-grid">${grupos[g].map(_tarjetaKanban).join('')}</div>
            </div>`
        ).join('');
    }
}

function _tarjetaKanban(t) {
    const esBajo  = t.stock_actual <= t.stock_minimo;
    const tipoMap = { 'MANUAL': 'manual', 'AUTOMATICA': 'automatica', 'SEMI-AUTOMATICA': 'semi' };
    const tipoCls = t.tipo_operacion ? (tipoMap[t.tipo_operacion] || 'manual') : 'sin-asignar';
    const tipoLbl = t.tipo_operacion
        ? { 'MANUAL': '🤚 Manual', 'AUTOMATICA': '🤖 Auto', 'SEMI-AUTOMATICA': '⚡ Semi' }[t.tipo_operacion] || t.tipo_operacion
        : '— Sin máquina';

    let badgeCls = 'ok';
    if (t.stock_actual === 0)              badgeCls = 'cero';
    else if (t.stock_actual <= t.stock_minimo) badgeCls = 'bajo';

    const cod = encodeURIComponent(t.terminal);

    return `
    <div class="kanban-card${esBajo ? ' alerta-stock' : ''}" id="kc-${t.terminal.replace(/[^a-zA-Z0-9]/g,'_')}">
        <div class="kc-header">
            <span class="kc-code">${t.terminal}</span>
            <span class="kc-tipo ${tipoCls}">${tipoLbl}</span>
        </div>
        <div class="kc-meta">
            <span class="kc-tag${t.maquina_nombre ? '' : ' sin-dato'}" title="Máquina">
                ⚙️ ${t.maquina_nombre || '—'}
            </span>
            <span class="kc-tag gaveta${t.gaveta ? '' : ' sin-dato'}" title="Gaveta">
                📦 ${t.gaveta || '—'}
            </span>
        </div>
        <div class="kc-archivos">📋 ${t.archivos.join(' · ') || '—'}</div>
        <div class="kc-stock-row">
            <span class="kc-stock-label">Stock:</span>
            <input class="kc-stock-input" type="number" min="0"
                   value="${t.stock_actual}"
                   data-original="${t.stock_actual}"
                   data-terminal="${t.terminal}"
                   oninput="kcStockChanged(this)"
                   title="Stock actual">
            <span class="kc-stock-label" style="font-size:0.72rem;">mín.</span>
            <input class="kc-stock-input" type="number" min="0"
                   value="${t.stock_minimo}"
                   data-original-min="${t.stock_minimo}"
                   data-terminal-min="${t.terminal}"
                   oninput="kcStockChanged(this)"
                   title="Stock mínimo" style="width:55px;">
            <span class="kc-stock-badge ${badgeCls}" id="kc-badge-${cod}">
                ${t.stock_actual === 0 ? '⚠ Vacío' : (esBajo ? '↓ Bajo' : '✓ OK')}
            </span>
            <button class="kc-save-btn" id="kc-save-${cod}" onclick="kcGuardarStock('${t.terminal}', this)">💾</button>
        </div>
        ${t.notas ? `<div class="kc-notas">📝 ${t.notas}</div>` : ''}
    </div>`;
}

function kcStockChanged(input) {
    // Mostrar botón guardar al modificar cualquiera de los dos inputs de la card
    const card = input.closest('.kanban-card');
    const saveBtn = card.querySelector('.kc-save-btn');
    if (saveBtn) saveBtn.classList.add('visible');
}

async function kcGuardarStock(terminal, btn) {
    const card        = btn.closest('.kanban-card');
    const inputs      = card.querySelectorAll('.kc-stock-input');
    const stockActual = parseInt(inputs[0].value) || 0;
    const stockMinimo = parseInt(inputs[1].value) || 0;
    btn.disabled = true;
    btn.textContent = '…';
    try {
        const resp = await fetch(`/api/terminal-stock/${encodeURIComponent(terminal)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stock_actual: stockActual, stock_minimo: stockMinimo })
        });
        const data = await resp.json();
        if (data.success) {
            // Actualizar datos locales
            const t = _kanbanData.find(x => x.terminal === terminal);
            if (t) { t.stock_actual = stockActual; t.stock_minimo = stockMinimo; }
            inputs[0].dataset.original    = stockActual;
            inputs[1].dataset.originalMin = stockMinimo;
            btn.classList.remove('visible');
            // Actualizar badge inline
            const cod     = encodeURIComponent(terminal);
            const badgeEl = document.getElementById('kc-badge-' + cod);
            const esBajo  = stockActual <= stockMinimo;
            if (badgeEl) {
                badgeEl.className = 'kc-stock-badge ' + (stockActual === 0 ? 'cero' : esBajo ? 'bajo' : 'ok');
                badgeEl.textContent = stockActual === 0 ? '⚠ Vacío' : (esBajo ? '↓ Bajo' : '✓ OK');
            }
            card.classList.toggle('alerta-stock', esBajo);
        } else {
            alert('Error al guardar: ' + (data.message || ''));
        }
    } catch (e) {
        alert('Error de conexión');
    } finally {
        btn.disabled = false;
        btn.textContent = '💾';
    }
}

function exportarExcelPedido() {
    window.location.href = '/api/kanban-terminales/export-excel';
}