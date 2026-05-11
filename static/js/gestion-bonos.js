// Gestión de Bonos - JavaScript

let proyectosDisponibles = [];

// Inicialización
document.addEventListener('DOMContentLoaded', function() {
    cargarProyectos();
    generarCarros();
    cargarBonosParaReportes();
    cargarBonosGestion();
});

// Tabs
function mostrarTab(tab) {
    // Ocultar todos los tabs
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    
    // Mostrar tab seleccionado
    document.getElementById(`tab-${tab}`).classList.add('active');
    event.target.classList.add('active');
}

// Cargar proyectos disponibles
async function cargarProyectos() {
    try {
        const response = await fetch('/api/archivos');
        const data = await response.json();
        
        if (data.success) {
            proyectosDisponibles = data.archivos;
        }
    } catch (error) {
        console.error('Error al cargar proyectos:', error);
    }
}

// Generar selectores de carros
function generarCarros() {
    const container = document.getElementById('carros-container');
    container.innerHTML = '';
    
    for (let i = 1; i <= 6; i++) {
        const carroDiv = document.createElement('div');
        carroDiv.className = 'carro-config';
        carroDiv.innerHTML = `
            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                <h4 style="margin: 0 0 10px 0;">🚛 Carro ${i}</h4>
                <div class="input-group" style="margin-bottom: 10px;">
                    <label>Proyecto:</label>
                    <select id="carro-${i}-proyecto" onchange="actualizarNombreProyecto(${i})">
                        <option value="">-- Vacío --</option>
                        ${proyectosDisponibles.map(p => `<option value="${p}">${p}</option>`).join('')}
                    </select>
                </div>
                <div class="input-group">
                    <label>Nombre del Proyecto:</label>
                    <input type="text" id="carro-${i}-nombre" placeholder="Ej: ITALIA, BADEN, etc.">
                </div>
            </div>
        `;
        container.appendChild(carroDiv);
    }
}

// Actualizar nombre del proyecto basado en el archivo
function actualizarNombreProyecto(numCarro) {
    const select = document.getElementById(`carro-${numCarro}-proyecto`);
    const inputNombre = document.getElementById(`carro-${numCarro}-nombre`);
    
    if (select.value) {
        // Extraer nombre del proyecto del archivo
        const nombreArchivo = select.value;
        const match = nombreArchivo.match(/CAB_([A-Z_]+)_/);
        if (match) {
            inputNombre.value = match[1];
        }
    } else {
        inputNombre.value = '';
    }
}

// Crear bono
document.getElementById('form-crear-bono')?.addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const nombreBono = document.getElementById('nombre-bono').value.trim();
    const numCortes = parseInt(document.getElementById('num-cortes').value);
    
    // Recopilar carros
    const carros = [];
    for (let i = 1; i <= 6; i++) {
        const proyecto = document.getElementById(`carro-${i}-proyecto`).value;
        if (proyecto) {
            carros.push({
                carro: i,
                archivo_excel: proyecto,
                proyecto_nombre: document.getElementById(`carro-${i}-nombre`).value.trim() || `Carro ${i}`
            });
        }
    }
    
    if (carros.length === 0) {
        mostrarMensaje('crear', 'Debes asignar al menos un carro', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/bonos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                nombre: nombreBono,
                num_cortes: numCortes,
                carros: carros
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            mostrarMensaje('crear', '✅ Bono creado exitosamente', 'success');
            document.getElementById('form-crear-bono').reset();
            generarCarros(); // Regenerar carros
        } else {
            mostrarMensaje('crear', `❌ Error: ${data.message}`, 'error');
        }
    } catch (error) {
        mostrarMensaje('crear', '❌ Error al crear el bono', 'error');
        console.error(error);
    }
});

// Cargar bonos para gestión (editar/eliminar)
async function cargarBonosGestion() {
    try {
        const response = await fetch('/api/bonos');
        const data = await response.json();
        
        const container = document.getElementById('lista-bonos-gestion');
        
        if (data.success && data.bonos.length > 0) {
            let html = '<table class="tabla-bonos"><thead><tr><th>Nombre</th><th>Cortes</th><th>Carros</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>';
            
            data.bonos.forEach(bono => {
                html += `
                    <tr>
                        <td><strong>${bono.nombre}</strong></td>
                        <td>${bono.num_cortes}</td>
                        <td>${bono.carros.length}</td>
                        <td><span class="badge ${bono.activo ? 'badge-success' : 'badge-secondary'}">${bono.activo ? 'Activo' : 'Inactivo'}</span></td>
                        <td>
                            <button class="btn-small btn-warning" onclick="editarBono('${bono.nombre}')">✏️ Editar</button>
                            <button class="btn-small btn-danger" onclick="eliminarBono('${bono.nombre}')">🗑️ Eliminar</button>
                        </td>
                    </tr>
                `;
            });
            
            html += '</tbody></table>';
            container.innerHTML = html;
        } else {
            container.innerHTML = '<p class="text-muted">No hay bonos registrados</p>';
        }
    } catch (error) {
        console.error('Error al cargar bonos:', error);
    }
}

// Eliminar bono
async function eliminarBono(nombreBono) {
    if (!confirm(`¿Estás seguro de eliminar el bono "${nombreBono}"? Esta acción no se puede deshacer.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/bonos/${nombreBono}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('✅ Bono eliminado correctamente');
            cargarBonosGestion();
        } else {
            alert(`❌ Error: ${data.message}`);
        }
    } catch (error) {
        alert('❌ Error al eliminar el bono');
        console.error(error);
    }
}

// Editar bono (placeholder - por implementar)
function editarBono(nombreBono) {
    alert(`Funcionalidad de edición en desarrollo para: ${nombreBono}`);
    // TODO: Implementar modal de edición
}

// Cargar bonos para reportes
async function cargarBonosParaReportes() {
    try {
        const response = await fetch('/api/bonos');
        const data = await response.json();
        
        const select = document.getElementById('select-bono-reporte');
        select.innerHTML = '<option value="">-- Seleccionar bono --</option>';
        
        if (data.success) {
            data.bonos.forEach(bono => {
                select.innerHTML += `<option value="${bono.nombre}">${bono.nombre} (${bono.num_cortes} cortes)</option>`;
            });
        }
    } catch (error) {
        console.error('Error al cargar bonos:', error);
    }
}

// Generar reporte
async function generarReporte() {
    const nombreBono = document.getElementById('select-bono-reporte').value;
    
    if (!nombreBono) {
        alert('Por favor selecciona un bono');
        return;
    }
    
    try {
        const response = await fetch(`/api/bonos/${nombreBono}/reporte`);
        const data = await response.json();
        
        if (data.success) {
            mostrarReporte(data.reporte, nombreBono);
        } else {
            alert(`❌ Error: ${data.message}`);
        }
    } catch (error) {
        alert('❌ Error al generar el reporte');
        console.error(error);
    }
}

// Mostrar reporte
function mostrarReporte(reporte, nombreBono) {
    const container = document.getElementById('reporte-contenido');
    
    let html = `
        <div class="reporte-card">
            <div class="reporte-header">
                <h3>📊 Reporte: ${nombreBono}</h3>
                <button onclick="descargarReporte('${nombreBono}')" class="btn-secondary">💾 Descargar CSV</button>
            </div>
            
            <div class="reporte-stats">
                <div class="stat-box">
                    <div class="stat-value">${reporte.total_terminales || 0}</div>
                    <div class="stat-label">Terminales Trabajados</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${reporte.total_carros || 0}</div>
                    <div class="stat-label">Carros Completados</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${reporte.progreso_general || 0}%</div>
                    <div class="stat-label">Progreso General</div>
                </div>
            </div>
            
            <h4 style="margin-top: 30px;">Detalle por Terminal</h4>
            <table class="tabla-reporte">
                <thead>
                    <tr>
                        <th>Terminal</th>
                        <th>Carros Completados</th>
                        <th>Fecha/Hora</th>
                        <th>Estado</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    if (reporte.detalle && reporte.detalle.length > 0) {
        reporte.detalle.forEach(item => {
            html += `
                <tr>
                    <td><strong>${item.terminal}</strong></td>
                    <td>${item.carros_completados.join(', ')}</td>
                    <td>${item.fecha_hora || 'N/A'}</td>
                    <td><span class="badge ${item.estado === 'completado' ? 'badge-success' : 'badge-warning'}">${item.estado}</span></td>
                </tr>
            `;
        });
    } else {
        html += '<tr><td colspan="4" style="text-align: center;">No hay datos disponibles</td></tr>';
    }
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    container.innerHTML = html;
}

// Descargar reporte como CSV
async function descargarReporte(nombreBono) {
    try {
        const response = await fetch(`/api/bonos/${nombreBono}/reporte`);
        const data = await response.json();
        
        if (!data.success) {
            alert('Error al generar el reporte');
            return;
        }
        
        // Generar CSV
        let csv = 'Terminal,Carros Completados,Fecha/Hora,Estado\n';
        
        if (data.reporte.detalle) {
            data.reporte.detalle.forEach(item => {
                csv += `"${item.terminal}","${item.carros_completados.join(', ')}","${item.fecha_hora || 'N/A'}","${item.estado}"\n`;
            });
        }
        
        // Descargar archivo
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `reporte_${nombreBono}_${new Date().toISOString().slice(0,10)}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
        
    } catch (error) {
        alert('Error al descargar el reporte');
        console.error(error);
    }
}

// Utilidad: mostrar mensajes
function mostrarMensaje(tipo, mensaje, clase) {
    const mensajeEl = document.getElementById(`mensaje-${tipo}`);
    mensajeEl.textContent = mensaje;
    mensajeEl.className = `mensaje ${clase}`;
    mensajeEl.classList.remove('hidden');
    
    setTimeout(() => {
        mensajeEl.classList.add('hidden');
    }, 5000);
}
