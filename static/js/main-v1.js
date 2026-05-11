/**
 * Sistema de Engastado Automático
 * JavaScript Principal - Operación
 */

// Variables globales
let archivoActual = null;
let terminalActual = null;

// Inicialización
document.addEventListener('DOMContentLoaded', function() {
    const codigoCorteInput = document.getElementById('codigo-corte');
    const codigoTerminalInput = document.getElementById('codigo-terminal');
    
    // Event listener para código de corte
    if (codigoCorteInput) {
        codigoCorteInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                cargarCorte();
            }
        });
    }
    
    // Event listener para código de terminal
    if (codigoTerminalInput) {
        codigoTerminalInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                buscarTerminal();
            }
        });
    }
});

/**
 * Cargar archivo Excel por código de barras
 */
async function cargarCorte() {
    const codigoCorte = document.getElementById('codigo-corte').value.trim();
    
    if (!codigoCorte) {
        mostrarMensaje('Por favor, escanea un código de corte', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/cargar_corte', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ codigo_barras: codigoCorte })
        });
        
        const data = await response.json();
        
        if (data.success) {
            archivoActual = data.archivo;
            document.getElementById('archivo-nombre').textContent = data.archivo;
            document.getElementById('corte-info').classList.remove('hidden');
            document.getElementById('paso2').classList.remove('hidden');
            
            // Enfocar el input de terminal
            document.getElementById('codigo-terminal').focus();
            
            mostrarMensaje('Archivo cargado correctamente', 'success');
        } else {
            mostrarMensaje(data.message, 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al cargar el archivo', 'error');
    }
}

/**
 * Buscar terminal en el archivo cargado
 */
async function buscarTerminal() {
    const terminal = document.getElementById('codigo-terminal').value.trim();
    
    if (!terminal) {
        mostrarMensaje('Por favor, escanea un terminal', 'error');
        return;
    }
    
    if (!archivoActual) {
        mostrarMensaje('Primero debes cargar un archivo Excel', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/buscar_terminal', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ terminal: terminal })
        });
        
        const data = await response.json();
        
        if (data.success) {
            terminalActual = data.terminal;
            mostrarResultados(data);
        } else {
            mostrarMensaje(data.message, 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al buscar el terminal', 'error');
    }
}

/**
 * Mostrar resultados en tarjetas
 */
function mostrarResultados(data) {
    // Actualizar información del terminal
    document.getElementById('terminal-actual').textContent = data.terminal;
    document.getElementById('total-grupos').textContent = data.total_grupos;
    document.getElementById('total-terminales').textContent = data.total_terminales || 0;
    
    // Generar tarjetas
    const container = document.getElementById('tarjetas-container');
    container.innerHTML = '';
    
    data.grupos.forEach((grupo, index) => {
        const tarjeta = crearTarjeta(grupo, index);
        container.appendChild(tarjeta);
    });
    
    // Agregar listener para actualizar contador de completadas
    actualizarContadorCompletadas();
    document.getElementById('tarjetas-container').addEventListener('click', function(e) {
        if (e.target.closest('.tarjeta-grupo')) {
            setTimeout(actualizarContadorCompletadas, 100);
        }
    });
    
    // Mostrar sección de resultados
    document.getElementById('resultados').classList.remove('hidden');
    
    // Scroll a los resultados
    document.getElementById('resultados').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Actualizar contador de tarjetas completadas
 */
function actualizarContadorCompletadas() {
    const total = document.querySelectorAll('.tarjeta-grupo').length;
    const completadas = document.querySelectorAll('.tarjeta-grupo.completada').length;
    const pendientes = total - completadas;
    
    document.getElementById('total-grupos').textContent = total;
    
    // Actualizar o crear indicador de progreso
    let indicador = document.getElementById('indicador-progreso');
    if (!indicador) {
        indicador = document.createElement('span');
        indicador.id = 'indicador-progreso';
        indicador.style.marginLeft = '10px';
        indicador.style.fontSize = '14px';
        document.getElementById('terminal-actual').parentElement.appendChild(indicador);
    }
    
    if (completadas > 0) {
        indicador.textContent = `(${completadas} completadas, ${pendientes} pendientes)`;
        indicador.style.color = completadas === total ? '#10b981' : '#f59e0b';
    } else {
        indicador.textContent = '';
    }
}

/**
 * Crear tarjeta de grupo
 */
function crearTarjeta(grupo, index) {
    const tarjeta = document.createElement('div');
    tarjeta.className = 'tarjeta-grupo';
    
    // Agregar evento click para marcar como completada
    tarjeta.addEventListener('click', function(e) {
        // No hacer nada si se hace click en un badge de cable (para posible futura funcionalidad)
        if (e.target.classList.contains('cable-badge')) {
            return;
        }
        this.classList.toggle('completada');
    });
    
    // ALARMA: Solo cuando un mismo cable lleva terminal en AMBAS puntas (sin números, solo aviso)
    const advertenciaDobleTerminal = grupo.cables_doble_terminal && grupo.cables_doble_terminal.length > 0 ? `
        <div class="alerta-doble-terminal-compacta">
            <span class="cable-badge cable-doble-terminal">🔌</span> TERMINAL AMBAS PUNTAS
        </div>
    ` : '';
    
    // Obtener TODOS los cables del grupo (desde el backend)
    const todosCables = grupo.todos_cables || [];
    
    // Sección de cables - mostrar TODOS los cables del grupo
    const seccionCables = todosCables.length > 0 ? `
        <div class="cables-section">
            <p><strong>Cables:</strong></p>
            <div class="cables-container">
                ${todosCables.map(cable => {
                    const esDobleTerminal = grupo.cables_doble_terminal && grupo.cables_doble_terminal.includes(cable);
                    const esSimple = grupo.cables_simple && grupo.cables_simple.includes(cable);
                    let claseExtra = '';
                    if (esDobleTerminal) {
                        claseExtra = 'cable-doble-terminal';  // ROJO
                    } else if (esSimple) {
                        claseExtra = 'cable-simple';  // AZUL
                    }
                    return `<span class="cable-badge ${claseExtra}">${cable}</span>`;
                }).join('')}
            </div>
        </div>
    ` : '';
    
    tarjeta.innerHTML = `
        <div class="tarjeta-header">
            <h3>${grupo.elemento}</h3>
            <div class="elemento">Cable: ${grupo.cod_cable}</div>
        </div>
        
        <div class="tarjeta-info-compacta">
            <span><strong>Cables:</strong> ${grupo.num_cables}</span>
            <span><strong>Terminales:</strong> ${grupo.num_terminales}</span>
            <span><strong>Sección:</strong> ${grupo.seccion || 'N/A'}</span>
        </div>
        
        ${advertenciaDobleTerminal}
        ${seccionCables}
    `;
    
    return tarjeta;
}

/**
 * Crear HTML para cada conexión
 */
function crearConexionHTML(conexion) {
    return `
        <div class="conexion-item">
            <div>
                <span class="cable-marca">Cables: ${conexion.cables_marca_str}</span>
            </div>
            <div class="conexion-detalle">
                <strong>Destino:</strong> ${conexion.para_elemento} → Pto. ${conexion.para_pto_conexion} → Terminal ${conexion.para_terminal}
            </div>
        </div>
    `;
}

/**
 * Escanear otro terminal (mantener archivo cargado)
 */
function escanearOtroTerminal() {
    document.getElementById('codigo-terminal').value = '';
    document.getElementById('resultados').classList.add('hidden');
    document.getElementById('codigo-terminal').focus();
}

/**
 * Nuevo escaneo (cambiar archivo)
 */
function nuevoEscaneo() {
    // Resetear todo
    document.getElementById('codigo-corte').value = '';
    document.getElementById('codigo-terminal').value = '';
    document.getElementById('corte-info').classList.add('hidden');
    document.getElementById('paso2').classList.add('hidden');
    document.getElementById('resultados').classList.add('hidden');
    
    archivoActual = null;
    terminalActual = null;
    
    // Enfocar primer input
    document.getElementById('codigo-corte').focus();
}

/**
 * Mostrar mensaje al usuario
 */
function mostrarMensaje(texto, tipo = 'info') {
    const mensajeDiv = document.getElementById('mensaje');
    mensajeDiv.textContent = texto;
    mensajeDiv.className = `mensaje ${tipo}`;
    mensajeDiv.classList.remove('hidden');
    
    // Ocultar después de 5 segundos
    setTimeout(() => {
        mensajeDiv.classList.add('hidden');
    }, 5000);
}
