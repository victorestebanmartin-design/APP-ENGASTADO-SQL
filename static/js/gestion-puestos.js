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
 * Mostrar lista de asignaciones
 */
function mostrarAsignaciones(dataTerminales, maquinas) {
    // Actualizar estadísticas
    document.getElementById('total-terminales').textContent = `${dataTerminales.total} terminales`;
    document.getElementById('sin-asignar').textContent = `${dataTerminales.sin_asignar} sin asignar`;
    
    // Mostrar alerta si hay terminales sin asignar
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
    
    // Crear selector de máquinas para asignación rápida
    const selectorMaquinas = maquinas.map(m => 
        `<option value="${m.id}">${m.puesto_nombre} - ${m.nombre}</option>`
    ).join('');
    
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
        
        <div class="terminales-grid" id="terminales-grid">
            ${dataTerminales.terminales.map(terminal => `
                <div class="terminal-card ${terminal.asignado ? 'asignado' : 'sin-asignar'}" 
                     data-terminal="${terminal.terminal}" 
                     data-estado="${terminal.asignado ? 'asignado' : 'sin-asignar'}">
                    <div class="terminal-header">
                        <input type="checkbox" class="terminal-checkbox" value="${terminal.terminal}" 
                               ${terminal.asignado ? 'disabled' : ''}>
                        <span class="terminal-nombre">${terminal.terminal}</span>
                        <div class="terminal-actions">
                            ${terminal.asignado ? 
                                `<button class="btn-icon btn-desasignar" onclick="desasignarTerminal('${terminal.terminal}')" title="Desasignar">
                                    ❌
                                </button>` : 
                                `<button class="btn-icon btn-asignar" onclick="mostrarAsignacionRapida('${terminal.terminal}')" title="Asignar">
                                    ➕
                                </button>`
                            }
                        </div>
                    </div>
                    <div class="terminal-info">
                        ${terminal.asignado ? 
                            `<div class="asignacion-actual">
                                <strong>Asignado a:</strong><br>
                                <span class="maquina-info">${terminal.asignacion.puesto_nombre} - ${terminal.asignacion.maquina_nombre}</span>
                            </div>` :
                            `<div class="sin-asignacion">
                                <span class="estado-pendiente">⚠️ Pendiente de asignar</span>
                            </div>`
                        }
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    
    // Aplicar filtros iniciales
    aplicarFiltros();
}

/**
 * Aplicar filtros de visualización
 */
function aplicarFiltros() {
    const filtroEstado = document.getElementById('filtro-estado').value;
    const busqueda = document.getElementById('buscar-terminal').value.toLowerCase();
    const terminales = document.querySelectorAll('.terminal-card');
    
    terminales.forEach(terminal => {
        const nombreTerminal = terminal.querySelector('.terminal-nombre').textContent.toLowerCase();
        const estadoTerminal = terminal.dataset.estado;
        
        let mostrar = true;
        
        // Filtro por estado
        if (filtroEstado !== 'todos' && estadoTerminal !== filtroEstado.replace('-', '-')) {
            mostrar = false;
        }
        
        // Filtro por búsqueda
        if (busqueda && !nombreTerminal.includes(busqueda)) {
            mostrar = false;
        }
        
        terminal.style.display = mostrar ? 'block' : 'none';
    });
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
    
    const checkboxes = document.querySelectorAll('.terminal-checkbox:checked');
    if (checkboxes.length === 0) {
        alert('Selecciona al menos un terminal');
        return;
    }
    
    const terminales = Array.from(checkboxes).map(cb => cb.value);
    
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
    const maquinaSelect = document.getElementById('maquina-destino');
    const checkbox = document.querySelector(`input[value="${terminal}"]`);
    
    // Limpiar otras selecciones
    document.querySelectorAll('.terminal-checkbox').forEach(cb => cb.checked = false);
    
    // Seleccionar este terminal
    checkbox.checked = true;
    
    // Enfocar selector de máquina
    maquinaSelect.focus();
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