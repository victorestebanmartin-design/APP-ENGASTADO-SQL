/**
 * Sistema de Registro de Órdenes de Producción
 */

let todasLasOrdenes = []; // Array global para filtrado

// Inicialización
document.addEventListener('DOMContentLoaded', function() {
    cargarOrdenes();
    cargarCodigosCortes();
    establecerFechaActual();
    
    // Event listener para formulario de escaneo
    const formEscaneo = document.getElementById('form-escanear-orden');
    if (formEscaneo) {
        formEscaneo.addEventListener('submit', procesarCodigoBarras);
    }
    
    // Event listener para formulario manual
    const formOrden = document.getElementById('form-nueva-orden');
    if (formOrden) {
        formOrden.addEventListener('submit', registrarOrden);
    }
    
    // Event listener para cambio de código de corte
    const selectCodigoCorte = document.getElementById('orden-codigo-corte');
    if (selectCodigoCorte) {
        selectCodigoCorte.addEventListener('change', mostrarInfoArchivo);
    }
    
    // Auto-focus en el campo de código de barras
    const inputCodigo = document.getElementById('codigo-barras-orden');
    if (inputCodigo) {
        inputCodigo.focus();
    }
});

/**
 * Establecer fecha actual por defecto
 */
function establecerFechaActual() {
    const inputFecha = document.getElementById('orden-fecha');
    if (inputFecha) {
        const hoy = new Date();
        const year = hoy.getFullYear();
        const month = String(hoy.getMonth() + 1).padStart(2, '0');
        const day = String(hoy.getDate()).padStart(2, '0');
        inputFecha.value = `${year}-${month}-${day}`;
    }
}

/**
 * Cargar códigos de corte disponibles
 */
async function cargarCodigosCortes() {
    try {
        const response = await fetch('/api/codigos_cortes/listar');
        const data = await response.json();
        
        if (data.success && data.codigos) {
            const select = document.getElementById('orden-codigo-corte');
            if (select) {
                // Limpiar opciones existentes excepto la primera
                select.innerHTML = '<option value="">-- Seleccionar código --</option>';
                
                // Agregar códigos
                data.codigos.forEach(corte => {
                    const option = document.createElement('option');
                    option.value = corte.codigo;
                    option.textContent = `${corte.codigo} - ${corte.descripcion || corte.proyecto || ''}`;
                    option.dataset.archivo = corte.archivo;
                    select.appendChild(option);
                });
            }
        }
    } catch (error) {
        console.error('Error al cargar códigos de corte:', error);
    }
}

/**
 * Mostrar información del archivo asociado
 */
function mostrarInfoArchivo() {
    const select = document.getElementById('orden-codigo-corte');
    const infoDiv = document.getElementById('info-archivo');
    
    if (select && infoDiv) {
        const selectedOption = select.options[select.selectedIndex];
        const archivo = selectedOption.dataset.archivo;
        
        if (archivo) {
            infoDiv.textContent = `📄 ${archivo}`;
            infoDiv.style.color = '#0d6efd';
        } else {
            infoDiv.textContent = '';
        }
    }
}

/**
 * Procesar código de barras
 * Formato: CODIGO_CORTE-ORDEN-CANTIDAD-FECHA
 * Ejemplo: CORTE001-OP2024-50-20251215
 */
async function procesarCodigoBarras(e) {
    e.preventDefault();
    
    const codigoCompleto = document.getElementById('codigo-barras-orden').value.trim();
    
    if (!codigoCompleto) {
        mostrarMensaje('mensaje-escaneo', 'Por favor escanea un código de barras', 'error');
        return;
    }
    
    // Separar por guiones
    const partes = codigoCompleto.split('-');
    
    if (partes.length !== 4) {
        mostrarMensaje('mensaje-escaneo', 
            `Formato incorrecto. Esperado: CODIGO-ORDEN-CANTIDAD-FECHA. Recibido: ${partes.length} partes`, 
            'error'
        );
        return;
    }
    
    const [codigoCorte, numeroOrden, cantidadStr, fechaStr] = partes;
    
    // Validar cantidad
    const cantidad = parseInt(cantidadStr);
    if (isNaN(cantidad) || cantidad <= 0) {
        mostrarMensaje('mensaje-escaneo', `Cantidad inválida: ${cantidadStr}`, 'error');
        return;
    }
    
    // Validar y formatear fecha (YYYYMMDD -> YYYY-MM-DD)
    if (fechaStr.length !== 8 || isNaN(fechaStr)) {
        mostrarMensaje('mensaje-escaneo', `Fecha inválida: ${fechaStr}. Debe ser YYYYMMDD`, 'error');
        return;
    }
    
    const year = fechaStr.substring(0, 4);
    const month = fechaStr.substring(4, 6);
    const day = fechaStr.substring(6, 8);
    const fechaEntrega = `${year}-${month}-${day}`;
    
    // Validar que sea una fecha válida
    const fecha = new Date(fechaEntrega);
    if (isNaN(fecha.getTime())) {
        mostrarMensaje('mensaje-escaneo', `Fecha inválida: ${fechaEntrega}`, 'error');
        return;
    }
    
    // Calcular prioridad automática basada en la fecha
    const hoy = new Date();
    const diasRestantes = Math.ceil((fecha - hoy) / (1000 * 60 * 60 * 24));
    let prioridad = 'media';
    
    if (diasRestantes < 0) {
        prioridad = 'urgente'; // Fecha pasada
    } else if (diasRestantes <= 3) {
        prioridad = 'urgente';
    } else if (diasRestantes <= 7) {
        prioridad = 'alta';
    } else if (diasRestantes <= 14) {
        prioridad = 'media';
    } else {
        prioridad = 'baja';
    }
    
    // Crear la orden automáticamente
    try {
        const response = await fetch('/api/ordenes/crear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                codigo_corte: codigoCorte,
                numero: numeroOrden,
                proyecto: '', // Se puede agregar después manualmente
                descripcion: `Orden escaneada: ${codigoCompleto}`,
                cantidad: cantidad,
                fecha_entrega: fechaEntrega,
                prioridad: prioridad
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            let mensaje = `✅ Orden registrada: ${numeroOrden} - ${cantidad} cables - Entrega: ${fechaEntrega} - Prioridad: ${prioridad}`;
            
            // Agregar información sobre asociación de Excel
            if (data.archivo_encontrado) {
                mensaje += ` - ✓ Excel asociado`;
            } else {
                mensaje += ` - ⚠ Sin Excel asociado`;
            }
            
            mostrarMensaje('mensaje-escaneo', mensaje, 'success');
            
            // Limpiar campo
            document.getElementById('codigo-barras-orden').value = '';
            
            // Recargar lista
            setTimeout(() => {
                cargarOrdenes();
                document.getElementById('codigo-barras-orden').focus();
            }, 1000);
        } else {
            mostrarMensaje('mensaje-escaneo', data.message || 'Error al registrar la orden', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('mensaje-escaneo', 'Error al registrar la orden', 'error');
    }
}

/**
 * Toggle formulario manual
 */
function toggleFormularioManual() {
    const form = document.getElementById('form-nueva-orden');
    if (form.style.display === 'none') {
        form.style.display = 'block';
        // Establecer valores por defecto cada vez que se abre
        establecerFechaActual();
        document.getElementById('orden-cantidad').value = '1';
    } else {
        form.style.display = 'none';
    }
}

/**
 * Registrar nueva orden (manual)
 */
async function registrarOrden(e) {
    e.preventDefault();
    
    const form = document.getElementById('form-nueva-orden');
    
    // Verificar si estamos editando
    if (form.dataset.editingId) {
        await actualizarOrden(form.dataset.editingId);
        return;
    }
    
    const codigoCorte = document.getElementById('orden-codigo-corte').value.trim();
    const numero = document.getElementById('orden-numero').value.trim();
    const cantidad = document.getElementById('orden-cantidad').value;
    const fecha = document.getElementById('orden-fecha').value;
    
    if (!codigoCorte || !numero || !cantidad || !fecha) {
        mostrarMensaje('mensaje-orden', 'Por favor completa todos los campos obligatorios', 'error');
        return;
    }
    
    // Calcular prioridad automática basada en la fecha
    const fechaOrden = new Date(fecha);
    const hoy = new Date();
    const diasRestantes = Math.ceil((fechaOrden - hoy) / (1000 * 60 * 60 * 24));
    let prioridad = 'media';
    
    if (diasRestantes < 0) {
        prioridad = 'urgente';
    } else if (diasRestantes <= 3) {
        prioridad = 'urgente';
    } else if (diasRestantes <= 7) {
        prioridad = 'alta';
    } else if (diasRestantes <= 14) {
        prioridad = 'media';
    } else {
        prioridad = 'baja';
    }
    
    try {
        const response = await fetch('/api/ordenes/crear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                codigo_corte: codigoCorte,
                numero,
                proyecto: '',
                descripcion: '',
                cantidad: parseInt(cantidad),
                fecha_entrega: fecha,
                prioridad
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            mostrarMensaje('mensaje-orden', '✅ Orden registrada correctamente', 'success');
            
            // Limpiar formulario y restablecer valores por defecto
            document.getElementById('form-nueva-orden').reset();
            document.getElementById('orden-codigo-corte').value = '';
            document.getElementById('orden-cantidad').value = '1';
            establecerFechaActual();
            document.getElementById('info-archivo').textContent = '';
            
            // Recargar lista
            setTimeout(() => {
                cargarOrdenes();
            }, 1000);
        } else {
            mostrarMensaje('mensaje-orden', data.message || 'Error al registrar la orden', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('mensaje-orden', 'Error al registrar la orden', 'error');
    }
}

/**
 * Cargar lista de órdenes
 */
async function cargarOrdenes() {
    const container = document.getElementById('lista-ordenes');
    container.innerHTML = '<p class="text-muted">Cargando...</p>';
    
    try {
        const response = await fetch('/api/ordenes/listar');
        const data = await response.json();
        
        if (data.success && data.ordenes) {
            todasLasOrdenes = data.ordenes; // Guardar todas las órdenes
            aplicarFiltros(); // Aplicar filtros actuales
        } else {
            container.innerHTML = '<p class="text-muted">No hay órdenes registradas</p>';
        }
    } catch (error) {
        console.error('Error:', error);
        container.innerHTML = '<p class="error">Error al cargar las órdenes</p>';
    }
}

/**
 * Aplicar filtros a las órdenes
 */
function aplicarFiltros() {
    const busqueda = document.getElementById('filtro-busqueda')?.value.toLowerCase() || '';
    const estado = document.getElementById('filtro-estado')?.value || '';
    const prioridad = document.getElementById('filtro-prioridad')?.value || '';
    const fechaDesde = document.getElementById('filtro-fecha-desde')?.value || '';
    const fechaHasta = document.getElementById('filtro-fecha-hasta')?.value || '';
    
    let ordenesFiltradas = todasLasOrdenes.filter(orden => {
        // Filtro de búsqueda (número, código, proyecto)
        const textoBusqueda = `${orden.numero} ${orden.codigo_corte} ${orden.proyecto || ''}`.toLowerCase();
        if (busqueda && !textoBusqueda.includes(busqueda)) {
            return false;
        }
        
        // Filtro de estado
        if (estado && orden.estado !== estado) {
            return false;
        }
        
        // Filtro de prioridad
        if (prioridad && orden.prioridad !== prioridad) {
            return false;
        }
        
        // Filtro de fecha desde
        if (fechaDesde && orden.fecha_entrega < fechaDesde) {
            return false;
        }
        
        // Filtro de fecha hasta
        if (fechaHasta && orden.fecha_entrega > fechaHasta) {
            return false;
        }
        
        return true;
    });
    
    mostrarOrdenes(ordenesFiltradas);
    actualizarEstadisticas(ordenesFiltradas);
}

/**
 * Limpiar todos los filtros
 */
function limpiarFiltros() {
    document.getElementById('filtro-busqueda').value = '';
    document.getElementById('filtro-estado').value = '';
    document.getElementById('filtro-prioridad').value = '';
    document.getElementById('filtro-fecha-desde').value = '';
    document.getElementById('filtro-fecha-hasta').value = '';
    aplicarFiltros();
}

/**
 * Mostrar órdenes en tabla
 */
function mostrarOrdenes(ordenes) {
    const container = document.getElementById('lista-ordenes');
    
    if (ordenes.length === 0) {
        container.innerHTML = '<p class="text-muted">No hay órdenes que coincidan con los filtros</p>';
        return;
    }
    
    let html = `
        <div style="margin-bottom: 10px; color: #6c757d; font-size: 0.9em;">
            Mostrando <strong>${ordenes.length}</strong> de <strong>${todasLasOrdenes.length}</strong> órdenes
        </div>
        <table class="tabla-datos">
            <thead>
                <tr>
                    <th>Código Corte</th>
                    <th style="max-width: 200px;">Archivo Excel</th>
                    <th>Número Orden</th>
                    <th>Cantidad</th>
                    <th>Fecha Liberación</th>
                    <th>Estado</th>
                    <th>Bono</th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    ordenes.forEach(orden => {
        // Estados con badges profesionales
        const estadoBadge = {
            'pendiente': '<span style="display:inline-block; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; background: #e2e3e5; color: #383d41;">Pendiente</span>',
            'en_bono': '<span style="display:inline-block; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; background: #cfe2ff; color: #084298;">En Bono</span>',
            'engastando': '<span style="display:inline-block; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; background: #fff3cd; color: #997404;">Engastando</span>',
            'finalizado': '<span style="display:inline-block; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; background: #d1e7dd; color: #0a3622;">Finalizado</span>'
        };
        
        const estadoActual = estadoBadge[orden.estado] || `<span style="color: #6c757d;">${orden.estado}</span>`;
        
        // Truncar nombre de archivo si es muy largo
        let archivoDisplay = '';
        if (orden.archivo_excel) {
            const nombreArchivo = orden.archivo_excel;
            archivoDisplay = `<div style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #0d6efd; font-size: 0.9em;" title="${nombreArchivo}">${nombreArchivo}</div>`;
        } else {
            archivoDisplay = '<span style="color: #dc3545; font-size: 0.85em;">No asociado</span>';
        }
        
        html += `
            <tr>
                <td><strong style="color: #212529;">${orden.codigo_corte || '-'}</strong></td>
                <td>${archivoDisplay}</td>
                <td style="font-weight: 500;">${orden.numero}</td>
                <td style="text-align: center; font-weight: 600;">${orden.cantidad}</td>
                <td style="font-size: 0.9em;">${formatearFecha(orden.fecha_entrega)}</td>
                <td>${estadoActual}</td>
                <td>${orden.bono ? `<strong style="color: #0d6efd;">${orden.bono}</strong>` : '<span style="color: #adb5bd;">-</span>'}</td>
                <td style="white-space: nowrap;">
                    ${orden.estado === 'pendiente' ? `
                        <button onclick="editarOrden('${orden.id}')" class="btn-small btn-secondary" style="margin-right: 5px;">Editar</button>
                    ` : ''}
                    <button onclick="eliminarOrden('${orden.id}', '${orden.estado}', '${orden.numero}')" class="btn-small btn-danger">Eliminar</button>
                </td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
    `;
    
    container.innerHTML = html;
}

/**
 * Actualizar estadísticas
 */
function actualizarEstadisticas(ordenes) {
    const total = ordenes.length;
    const pendientes = ordenes.filter(o => o.estado === 'pendiente').length;
    const enBono = ordenes.filter(o => o.estado === 'en_bono').length;
    const engastando = ordenes.filter(o => o.estado === 'engastando').length;
    const finalizadas = ordenes.filter(o => o.estado === 'finalizado').length;
    const urgentes = ordenes.filter(o => o.prioridad === 'urgente' && o.estado === 'pendiente').length;
    
    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-pendientes').textContent = pendientes;
    document.getElementById('stat-completadas').textContent = finalizadas;
    document.getElementById('stat-urgentes').textContent = urgentes;
}

/**
 * Eliminar orden
 */
async function eliminarOrden(id, estado, numeroOrden) {
    // Mensaje de advertencia según el estado
    let mensaje = '';
    
    switch(estado) {
        case 'pendiente':
            mensaje = `¿Eliminar la orden ${numeroOrden}?\n\nEsta acción no se puede deshacer.`;
            break;
        case 'en_bono':
            mensaje = `⚠️ ADVERTENCIA: La orden ${numeroOrden} está asignada a un bono.\n\nSi la eliminas, el bono quedará incompleto.\n\n¿Continuar con la eliminación?`;
            break;
        case 'engastando':
            mensaje = `⚠️ ADVERTENCIA: La orden ${numeroOrden} está siendo engastada.\n\nEliminarla puede causar inconsistencias en el proceso.\n\n¿Continuar de todos modos?`;
            break;
        case 'finalizado':
            mensaje = `La orden ${numeroOrden} ya está finalizada.\n\n¿Estás seguro de eliminarla del sistema?`;
            break;
        default:
            mensaje = `¿Eliminar la orden ${numeroOrden}?`;
    }
    
    if (!confirm(mensaje)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/ordenes/eliminar/${id}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('✅ Orden eliminada correctamente');
            cargarOrdenes();
        } else {
            alert('❌ Error al eliminar la orden: ' + (data.message || ''));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('❌ Error al eliminar la orden');
    }
}

/**
 * Editar orden
 */
async function editarOrden(id) {
    try {
        // Obtener la orden actual
        const response = await fetch('/api/ordenes/listar');
        const data = await response.json();
        
        if (!data.success) {
            alert('Error al cargar la orden');
            return;
        }
        
        const orden = data.ordenes.find(o => o.id === id);
        if (!orden) {
            alert('Orden no encontrada');
            return;
        }
        
        // Mostrar formulario manual con los datos
        const form = document.getElementById('form-nueva-orden');
        form.style.display = 'block';
        
        // Llenar el formulario
        document.getElementById('orden-codigo-corte').value = orden.codigo_corte || '';
        document.getElementById('orden-numero').value = orden.numero || '';
        document.getElementById('orden-proyecto').value = orden.proyecto || '';
        document.getElementById('orden-descripcion').value = orden.descripcion || '';
        document.getElementById('orden-cantidad').value = orden.cantidad || '';
        document.getElementById('orden-fecha').value = orden.fecha_entrega || '';
        document.getElementById('orden-prioridad').value = orden.prioridad || '';
        
        // Guardar el ID en un atributo del formulario
        form.dataset.editingId = id;
        
        // Cambiar texto del botón
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.textContent = '💾 Actualizar Orden';
        submitBtn.classList.remove('btn-primary');
        submitBtn.classList.add('btn-warning');
        
        // Agregar botón de cancelar
        let cancelBtn = document.getElementById('btn-cancelar-edicion');
        if (!cancelBtn) {
            cancelBtn = document.createElement('button');
            cancelBtn.id = 'btn-cancelar-edicion';
            cancelBtn.type = 'button';
            cancelBtn.className = 'btn-secondary';
            cancelBtn.textContent = '❌ Cancelar';
            cancelBtn.style.marginLeft = '10px';
            cancelBtn.onclick = cancelarEdicion;
            submitBtn.parentNode.insertBefore(cancelBtn, submitBtn.nextSibling);
        }
        
        // Scroll al formulario
        form.scrollIntoView({ behavior: 'smooth', block: 'start' });
        
    } catch (error) {
        console.error('Error:', error);
        alert('Error al cargar la orden para editar');
    }
}

/**
 * Actualizar orden existente
 */
async function actualizarOrden(id) {
    const codigoCorte = document.getElementById('orden-codigo-corte').value.trim();
    const numero = document.getElementById('orden-numero').value.trim();
    const proyecto = document.getElementById('orden-proyecto').value.trim();
    const descripcion = document.getElementById('orden-descripcion').value.trim();
    const cantidad = document.getElementById('orden-cantidad').value;
    const fecha = document.getElementById('orden-fecha').value;
    const prioridad = document.getElementById('orden-prioridad').value;
    
    if (!codigoCorte || !numero || !cantidad || !fecha || !prioridad) {
        mostrarMensaje('mensaje-orden', 'Por favor completa todos los campos obligatorios', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/ordenes/actualizar/${id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                codigo_corte: codigoCorte,
                numero,
                proyecto,
                descripcion,
                cantidad: parseInt(cantidad),
                fecha_entrega: fecha,
                prioridad
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            mostrarMensaje('mensaje-orden', 'Orden actualizada correctamente', 'success');
            cancelarEdicion();
            cargarOrdenes();
        } else {
            mostrarMensaje('mensaje-orden', data.message || 'Error al actualizar la orden', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('mensaje-orden', 'Error al actualizar la orden', 'error');
    }
}

/**
 * Cancelar edición
 */
function cancelarEdicion() {
    const form = document.getElementById('form-nueva-orden');
    form.reset();
    form.style.display = 'none';
    
    // Eliminar el ID de edición
    delete form.dataset.editingId;
    
    // Restaurar botón
    const submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.textContent = '✅ Registrar Orden';
    submitBtn.classList.remove('btn-warning');
    submitBtn.classList.add('btn-primary');
    
    // Eliminar botón de cancelar
    const cancelBtn = document.getElementById('btn-cancelar-edicion');
    if (cancelBtn) {
        cancelBtn.remove();
    }
    
    // Limpiar mensaje
    const mensaje = document.getElementById('mensaje-orden');
    mensaje.classList.add('hidden');
}

/**
 * Editar orden (placeholder - DEPRECATED)
 */
function editarOrdenOld(id) {
    alert('Función de edición en desarrollo. ID: ' + id);
}

/**
 * Formatear fecha
 */
function formatearFecha(fecha) {
    if (!fecha) return '-';
    const date = new Date(fecha);
    return date.toLocaleDateString('es-ES');
}

/**
 * Mostrar mensaje
 */
function mostrarMensaje(elementId, mensaje, tipo) {
    const elemento = document.getElementById(elementId);
    elemento.textContent = mensaje;
    elemento.className = `mensaje ${tipo}`;
    elemento.classList.remove('hidden');
    
    setTimeout(() => {
        elemento.classList.add('hidden');
    }, 5000);
}
