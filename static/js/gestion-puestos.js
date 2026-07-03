// ================================
// GESTIÓN DE PUESTOS Y MÁQUINAS
// ================================

let dataPuestos = null;
let dataMaquinas = null;

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
                ${maquinasPuesto.map(maquina => `
                    <div class="maquina-card" data-id="${maquina.id}">
                        <div class="maquina-header">
                            <h5>${maquina.nombre}</h5>
                            <div class="maquina-actions">
                                <button class="btn-icon" onclick="editarMaquina('${maquina.id}')" title="Editar">
                                    ✏️
                                </button>
                                <button class="btn-icon" onclick="eliminarMaquina('${maquina.id}')" title="Eliminar">
                                    🗑️
                                </button>
                            </div>
                        </div>
                        <p class="maquina-modelo">${maquina.modelo || 'Sin modelo'}</p>
                        <p class="maquina-descripcion">${maquina.descripcion || 'Sin descripción'}</p>
                        <div class="maquina-stats">
                            <span class="stat">
                                📱 ${maquina.terminales_asignados ? maquina.terminales_asignados.length : 0} terminales
                            </span>
                            <span class="stat-status ${maquina.activo ? 'activo' : 'inactivo'}">
                                ${maquina.activo ? '✅ Activa' : '❌ Inactiva'}
                            </span>
                        </div>
                    </div>
                `).join('')}
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
                
                console.log('Valores establecidos en el formulario:', {
                    puesto: document.getElementById('maquina-puesto').value,
                    nombre: document.getElementById('maquina-nombre').value,
                    modelo: document.getElementById('maquina-modelo').value,
                    descripcion: document.getElementById('maquina-descripcion').value
                });
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
    
    console.log('Datos a enviar:', { puestoId, nombre, modelo, descripcion, editId });
    
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
        
        console.log('Enviando petición:', method, url);
        
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                puesto_id: puestoId,
                nombre: nombre,
                modelo: modelo || '',
                descripcion: descripcion || ''
            })
        });
        
        console.log('Respuesta del servidor:', response.status, response.statusText);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Datos de respuesta:', data);
        
        if (data.success) {
            cerrarModal('modal-maquina');
            cargarMaquinas();
            mostrarNotificacion(editId ? 'Máquina actualizada correctamente' : 'Máquina creada correctamente', 'success');
        } else {
            alert('Error del servidor: ' + (data.message || 'Error desconocido'));
        }
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
                ${lista.map(t => `
                    <div class="terminal-row asignado"
                         data-terminal="${t.terminal}"
                         data-estado="asignados">
                        <span class="tr-check-spacer"></span>
                        ${imgThumb(t)}
                        <span class="tr-dot asignado"></span>
                        <span class="tr-code">${t.terminal}</span>
                        <span class="tr-assign asignado">${t.asignacion.puesto_nombre} · ${t.asignacion.maquina_nombre}</span>
                        ${gavetaChip(t)}
                        <span class="tr-badge asignado">Asignado</span>
                        <button class="btn-desvincular" onclick="desasignarTerminal('${t.terminal}')" title="Desasignar">✕</button>
                    </div>
                `).join('')}
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