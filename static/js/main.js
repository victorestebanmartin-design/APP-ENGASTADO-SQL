/**
 * Sistema de Engastado Automático V2.0
 * JavaScript Principal - Modo Interactivo
 */

// Variables globales
let archivoActual = null;
let terminalActual = null;
let gruposActuales = [];
let cajaActualIndex = -1;
let timerInterval = null;

// Inicialización
document.addEventListener('DOMContentLoaded', function() {
    const codigoCorteInput = document.getElementById('codigo-corte');
    
    // Event listener para código de corte
    if (codigoCorteInput) {
        codigoCorteInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                cargarCorte();
            }
        });
    }
});

/**
 * Cargar archivo Excel por código de barras y mostrar terminales disponibles
 */
async function cargarCorte() {
    const codigoCorte = document.getElementById('codigo-corte').value.trim();
    
    if (!codigoCorte) {
        mostrarMensaje('Por favor, escanea un código de corte', 'error');
        return;
    }
    
    try {
        // Cargar el corte
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
            
            mostrarMensaje('Archivo cargado correctamente', 'success');
            
            // Cargar lista de terminales disponibles
            await cargarListaTerminales();
        } else {
            mostrarMensaje(data.message, 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al cargar el archivo', 'error');
    }
}

/**
 * Cargar y mostrar lista de terminales disponibles
 */
async function cargarListaTerminales() {
    try {
        const response = await fetch('/api/listar_terminales');
        const data = await response.json();
        
        if (data.success && data.terminales.length > 0) {
            mostrarSeleccionTerminales(data.terminales);
        } else {
            mostrarMensaje('No se encontraron terminales en el archivo', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al cargar terminales', 'error');
    }
}

/**
 * Mostrar pantalla de selección de terminales
 */
function mostrarSeleccionTerminales(terminales) {
    const container = document.getElementById('seleccion-terminales-container');
    container.innerHTML = '';
    
    terminales.forEach(terminal => {
        const boton = document.createElement('button');
        boton.className = 'boton-terminal';
        boton.textContent = terminal;
        boton.onclick = () => seleccionarTerminal(terminal);
        container.appendChild(boton);
    });
    
    document.getElementById('seleccion-terminales').classList.remove('hidden');
    document.getElementById('paso2').classList.add('hidden');
}

/**
 * Seleccionar terminal y buscar grupos
 */
async function seleccionarTerminal(terminal) {
    terminalActual = terminal;
    
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
            gruposActuales = data.grupos;
            mostrarPantallaPaquetes(data);
        } else {
            mostrarMensaje(data.message, 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al buscar el terminal', 'error');
    }
}

/**
 * Mostrar pantalla de preparación - Recoger paquetes
 */
function mostrarPantallaPaquetes(data) {
    // Extraer elementos únicos (De Elemento)
    const elementosUnicos = [...new Set(data.grupos.map(g => g.elemento))];
    
    document.getElementById('terminal-paquetes').textContent = data.terminal;
    document.getElementById('num-paquetes').textContent = elementosUnicos.length;
    
    const listaPaquetes = document.getElementById('lista-paquetes');
    listaPaquetes.innerHTML = '';
    
    elementosUnicos.forEach((elemento, index) => {
        const li = document.createElement('li');
        li.className = 'paquete-item';
        li.innerHTML = `<span class="paquete-numero">${index + 1}</span> ${elemento}`;
        listaPaquetes.appendChild(li);
    });
    
    // Ocultar selección de terminales y mostrar preparación
    document.getElementById('seleccion-terminales').classList.add('hidden');
    document.getElementById('preparacion-paquetes').classList.remove('hidden');
}

/**
 * Confirmar paquetes y comenzar engastado
 */
function confirmarPaquetes() {
    document.getElementById('preparacion-paquetes').classList.add('hidden');
    mostrarModoEngastado();
}

/**
 * Mostrar modo engastado con cajas
 */
function mostrarModoEngastado() {
    const totalTerminales = gruposActuales.reduce((sum, g) => sum + g.num_terminales, 0);
    
    document.getElementById('terminal-actual').textContent = terminalActual;
    document.getElementById('total-grupos').textContent = gruposActuales.length;
    document.getElementById('total-terminales').textContent = totalTerminales;
    document.getElementById('grupos-completados').textContent = '0';
    
    // Generar tarjetas (pequeñas, bloqueadas excepto la primera)
    const container = document.getElementById('tarjetas-container');
    container.innerHTML = '';
    
    gruposActuales.forEach((grupo, index) => {
        const tarjeta = crearTarjetaPequena(grupo, index);
        container.appendChild(tarjeta);
    });
    
    // Mostrar sección de engastado
    document.getElementById('modo-engastado').classList.remove('hidden');
    
    // Inicializar en la primera caja
    cajaActualIndex = 0;
    habilitarCaja(0);
}

/**
 * Crear tarjeta pequeña (vista previa en lista)
 */
function crearTarjetaPequena(grupo, index) {
    const tarjeta = document.createElement('div');
    tarjeta.className = 'tarjeta-pequena bloqueada';
    tarjeta.id = `tarjeta-${index}`;
    tarjeta.dataset.index = index;
    
    tarjeta.innerHTML = `
        <div class="tarjeta-numero">${index + 1}</div>
        <div class="tarjeta-info-mini">
            <strong>${grupo.elemento}</strong>
            <span>${grupo.cod_cable}</span>
            <span class="badge-terminales">${grupo.num_terminales} term.</span>
        </div>
    `;
    
    tarjeta.onclick = () => intentarSeleccionarCaja(index);
    
    return tarjeta;
}

/**
 * Intentar seleccionar una caja (solo si está habilitada)
 */
function intentarSeleccionarCaja(index) {
    const tarjeta = document.getElementById(`tarjeta-${index}`);
    
    if (tarjeta.classList.contains('activa')) {
        mostrarCajaExpandida(index);
    } else if (tarjeta.classList.contains('bloqueada')) {
        mostrarMensaje('Debes completar la caja anterior primero', 'warning');
    }
}

/**
 * Habilitar una caja específica
 */
function habilitarCaja(index) {
    const tarjeta = document.getElementById(`tarjeta-${index}`);
    if (tarjeta) {
        tarjeta.classList.remove('bloqueada');
        tarjeta.classList.add('activa');
        
        // Scroll automático a la caja activa
        tarjeta.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

/**
 * Mostrar caja expandida (pantalla completa)
 */
function mostrarCajaExpandida(index) {
    const grupo = gruposActuales[index];
    const tiempoTotal = grupo.num_terminales * 3; // 3 segundos por terminal
    
    // Generar HTML de la caja expandida (igual que V1.0)
    const advertenciaDobleTerminal = grupo.cables_doble_terminal && grupo.cables_doble_terminal.length > 0 ? `
        <div class="alerta-doble-terminal-compacta">
            <span class="cable-badge cable-doble-terminal">🔌</span> TERMINAL AMBAS PUNTAS
        </div>
    ` : '';
    
    const todosCables = grupo.todos_cables || [];
    const seccionCables = todosCables.length > 0 ? `
        <div class="cables-section">
            <p><strong>Cables:</strong></p>
            <div class="cables-container">
                ${todosCables.map(cable => {
                    const esDobleTerminal = grupo.cables_doble_terminal && grupo.cables_doble_terminal.includes(cable);
                    const esSimple = grupo.cables_simple && grupo.cables_simple.includes(cable);
                    let claseExtra = '';
                    if (esDobleTerminal) {
                        claseExtra = 'cable-doble-terminal';
                    } else if (esSimple) {
                        claseExtra = 'cable-simple';
                    }
                    return `<span class="cable-badge ${claseExtra}">${cable}</span>`;
                }).join('')}
            </div>
        </div>
    ` : '';
    
    document.getElementById('caja-expandida-contenido').innerHTML = `
        <div class="caja-expandida-header">
            <h2>Grupo ${index + 1} de ${gruposActuales.length}</h2>
            <div class="elemento-grande">${grupo.elemento}</div>
            <div class="codigo-cable-grande">Cable: ${grupo.cod_cable}</div>
        </div>
        
        <div class="caja-expandida-info">
            <span><strong>Cables:</strong> ${grupo.num_cables}</span>
            <span><strong>Terminales:</strong> ${grupo.num_terminales}</span>
            <span><strong>Sección:</strong> ${grupo.seccion || 'N/A'}</span>
        </div>
        
        ${advertenciaDobleTerminal}
        ${seccionCables}
        
        <div class="timer-container">
            <div class="timer-texto">Engastando terminales...</div>
            <div class="timer-barra-fondo">
                <div class="timer-barra-progreso" id="timer-barra"></div>
            </div>
            <div class="timer-tiempo" id="timer-tiempo">${tiempoTotal}s</div>
        </div>
    `;
    
    // Mostrar caja expandida
    document.getElementById('caja-expandida').classList.remove('hidden');
    
    // Iniciar timer
    iniciarTimer(tiempoTotal, index);
}

/**
 * Iniciar timer de engastado
 */
function iniciarTimer(tiempoTotal, cajaIndex) {
    let tiempoRestante = tiempoTotal;
    const barra = document.getElementById('timer-barra');
    const textoTiempo = document.getElementById('timer-tiempo');
    
    // Limpiar timer anterior si existe
    if (timerInterval) {
        clearInterval(timerInterval);
    }
    
    timerInterval = setInterval(() => {
        tiempoRestante--;
        
        // Actualizar barra de progreso
        const progreso = ((tiempoTotal - tiempoRestante) / tiempoTotal) * 100;
        barra.style.width = progreso + '%';
        
        // Actualizar texto
        textoTiempo.textContent = tiempoRestante + 's';
        
        // Cuando termina el timer
        if (tiempoRestante <= 0) {
            clearInterval(timerInterval);
            completarCaja(cajaIndex);
        }
    }, 1000);
}

/**
 * Completar caja actual y pasar a la siguiente
 */
function completarCaja(index) {
    // Marcar tarjeta como completada
    const tarjeta = document.getElementById(`tarjeta-${index}`);
    tarjeta.classList.remove('activa');
    tarjeta.classList.add('completada');
    
    // Cerrar caja expandida
    document.getElementById('caja-expandida').classList.add('hidden');
    
    // Actualizar contador
    const completadas = index + 1;
    document.getElementById('grupos-completados').textContent = completadas;
    
    // Verificar si hay más cajas
    if (index + 1 < gruposActuales.length) {
        // Habilitar siguiente caja
        cajaActualIndex = index + 1;
        habilitarCaja(cajaActualIndex);
        mostrarMensaje('✅ Caja completada. Continúa con la siguiente', 'success');
    } else {
        // Todas las cajas completadas
        mostrarFinalizacion();
    }
}

/**
 * Mostrar pantalla de finalización
 */
function mostrarFinalizacion() {
    document.getElementById('modo-engastado').classList.add('hidden');
    document.getElementById('finalizacion').classList.remove('hidden');
    document.getElementById('terminal-finalizado').textContent = terminalActual;
    document.getElementById('total-completados').textContent = gruposActuales.length;
/**
 * Reiniciar para seleccionar otro terminal
 */
function seleccionarOtroTerminal() {
    // Resetear estado
    terminalActual = null;
    gruposActuales = [];
    cajaActualIndex = -1;
    
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    
    // Ocultar pantallas
    document.getElementById('finalizacion').classList.add('hidden');
    document.getElementById('modo-engastado').classList.add('hidden');
    document.getElementById('preparacion-paquetes').classList.add('hidden');
    document.getElementById('caja-expandida').classList.add('hidden');
    
    // Volver a cargar terminales
    cargarListaTerminales();
}

/**
 * Nuevo escaneo (cambiar archivo)
 */
function nuevoEscaneo() {
    // Resetear todo
    document.getElementById('codigo-corte').value = '';
    document.getElementById('corte-info').classList.add('hidden');
    document.getElementById('seleccion-terminales').classList.add('hidden');
    document.getElementById('preparacion-paquetes').classList.add('hidden');
    document.getElementById('modo-engastado').classList.add('hidden');
    document.getElementById('finalizacion').classList.add('hidden');
    document.getElementById('caja-expandida').classList.add('hidden');
    
    archivoActual = null;
    terminalActual = null;
    gruposActuales = [];
    cajaActualIndex = -1;
    
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    
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
