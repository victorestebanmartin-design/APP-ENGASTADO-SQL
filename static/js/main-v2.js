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
let progresoGuardado = {}; // Guardar progreso por terminal
let enterHandler = null; // Guardar referencia al handler de Enter
let esperandoEnterParaSiguiente = false; // Flag para saber si esperamos Enter para abrir siguiente caja

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
function mostrarSeleccionTerminales(terminalesData) {
    const container = document.getElementById('seleccion-terminales-container');
    container.innerHTML = '';
    
    terminalesData.forEach(item => {
        const terminal = item.terminal || item; // Compatibilidad con ambos formatos
        const desactivado = item.desactivado || false;
        
        const boton = document.createElement('button');
        boton.className = 'boton-terminal';
        boton.id = `boton-terminal-${terminal}`;
        boton.textContent = terminal;
        
        if (desactivado) {
            boton.classList.add('terminal-desactivado');
            boton.innerHTML = `<span class="desactivado-icon">🚫</span> ${terminal}`;
            boton.onclick = () => mostrarMensaje('Este terminal está desactivado', 'warning');
        } else {
            boton.onclick = () => seleccionarTerminal(terminal);
            
            // Marcar como completado si ya está en progreso guardado con todos los grupos completados
            if (progresoGuardado[terminal]) {
                const progreso = progresoGuardado[terminal];
                // Si tiene datos y la siguiente caja es el total, está completado
                if (progreso.totalGrupos && progreso.siguienteCaja >= progreso.totalGrupos) {
                    boton.classList.add('terminal-completado');
                    boton.innerHTML = `<span class="check-icon">✓</span> ${terminal}`;
                } else if (progreso.cajasCompletadas && progreso.cajasCompletadas.length > 0) {
                    // Si tiene progreso parcial, marcarlo como en progreso
                    boton.classList.add('terminal-en-progreso');
                    boton.innerHTML = `<span class="progreso-icon">⏳</span> ${terminal}`;
                }
            }
        }
        
        container.appendChild(boton);
    });
    
    document.getElementById('seleccion-terminales').classList.remove('hidden');
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
            
            // Verificar si hay progreso guardado
            const progreso = progresoGuardado[terminal];
            
            if (progreso && progreso.cajasCompletadas && progreso.cajasCompletadas.length > 0) {
                // Hay progreso, preguntar si quiere continuar o empezar de nuevo
                mostrarDialogoReanudar(data, progreso);
            } else {
                // No hay progreso, empezar desde el principio
                mostrarPantallaPaquetes(data);
            }
        } else {
            mostrarMensaje(data.message, 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al buscar el terminal', 'error');
    }
}

/**
 * Mostrar diálogo para reanudar o empezar de nuevo
 */
function mostrarDialogoReanudar(data, progreso) {
    const container = document.getElementById('seleccion-terminales-container');
    const completadas = progreso.cajasCompletadas.length;
    const total = data.grupos.length;
    
    container.innerHTML = `
        <div class="dialogo-reanudar">
            <div class="icono-info">📋</div>
            <h3>Progreso encontrado para ${data.terminal}</h3>
            <p class="progreso-info">Has completado <strong>${completadas} de ${total}</strong> grupos</p>
            <div class="dialogo-acciones">
                <button onclick="reanudarProgreso()" class="btn-reanudar">▶️ Continuar donde lo dejé</button>
                <button onclick="empezarDeNuevo()" class="btn-empezar-nuevo">🔄 Empezar de nuevo</button>
            </div>
        </div>
    `;
}

/**
 * Reanudar progreso guardado
 */
function reanudarProgreso() {
    document.getElementById('seleccion-terminales').classList.add('hidden');
    mostrarModoEngastado();
}

/**
 * Empezar de nuevo (borrar progreso)
 */
function empezarDeNuevo() {
    // Borrar progreso guardado
    delete progresoGuardado[terminalActual];
    
    // Buscar de nuevo para obtener los datos
    seleccionarTerminalNuevo(terminalActual);
}

/**
 * Seleccionar terminal sin verificar progreso (para empezar de nuevo)
 */
async function seleccionarTerminalNuevo(terminal) {
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
    
    // Inicializar progreso si no existe
    if (!progresoGuardado[terminalActual]) {
        progresoGuardado[terminalActual] = {
            cajasCompletadas: [],
            siguienteCaja: 0,
            totalGrupos: gruposActuales.length
        };
    } else {
        // Actualizar total de grupos por si cambió
        progresoGuardado[terminalActual].totalGrupos = gruposActuales.length;
    }
    
    // Verificar si hay progreso guardado
    const progreso = progresoGuardado[terminalActual];
    let gruposCompletadosCount = 0;
    
    if (progreso && progreso.cajasCompletadas) {
        gruposCompletadosCount = progreso.cajasCompletadas.length;
    }
    
    document.getElementById('grupos-completados').textContent = gruposCompletadosCount;
    
    // Generar tarjetas (pequeñas, bloqueadas excepto la primera o la última activa)
    const container = document.getElementById('tarjetas-container');
    container.innerHTML = '';
    
    gruposActuales.forEach((grupo, index) => {
        const tarjeta = crearTarjetaPequena(grupo, index);
        
        // Restaurar estado si ya estaba completada
        if (progreso && progreso.cajasCompletadas && progreso.cajasCompletadas.includes(index)) {
            tarjeta.classList.remove('bloqueada');
            tarjeta.classList.add('completada');
        }
        
        container.appendChild(tarjeta);
    });
    
    // Mostrar sección de engastado
    document.getElementById('modo-engastado').classList.remove('hidden');
    
    // Inicializar en la primera caja no completada
    if (progreso && progreso.siguienteCaja !== undefined) {
        cajaActualIndex = progreso.siguienteCaja;
    } else {
        cajaActualIndex = 0;
    }
    
    if (cajaActualIndex < gruposActuales.length) {
        habilitarCaja(cajaActualIndex);
    } else {
        // Ya completó todas las cajas
        mostrarFinalizacion();
    }
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
    
    // Separar cables en 3 grupos según la nueva lógica del backend
    const cablesDeTerminal = grupo.cables_de_terminal || [];      // Azules: solo en "De Terminal"
    const cablesParaTerminal = grupo.cables_para_terminal || [];  // Verdes: solo en "Para Terminal"  
    const cablesAmbos = grupo.cables_doble_terminal || [];        // Rojos: en ambas columnas
    
    // Generar HTML por grupos de terminales con colores
    const seccionTerminales = `
        <div class="terminales-groups">
            <h3>Terminales a engastar:</h3>
            <div class="terminals-grid">
                ${cablesDeTerminal.length > 0 ? `
                    <div class="terminal-group terminal-group-azul">
                        <div class="terminal-group-header">
                            <span class="terminal-group-icon">📍</span>
                            <span class="terminal-group-title">De Terminal</span>
                            <span class="terminal-group-count">${cablesDeTerminal.length}</span>
                        </div>
                        <div class="terminal-group-cables">
                            ${cablesDeTerminal.map(cable => 
                                `<span class="cable-badge cable-de-terminal">${cable}</span>`
                            ).join('')}
                        </div>
                    </div>
                ` : ''}
                
                ${cablesParaTerminal.length > 0 ? `
                    <div class="terminal-group terminal-group-verde">
                        <div class="terminal-group-header">
                            <span class="terminal-group-icon">🎯</span>
                            <span class="terminal-group-title">Para Terminal</span>
                            <span class="terminal-group-count">${cablesParaTerminal.length}</span>
                        </div>
                        <div class="terminal-group-cables">
                            ${cablesParaTerminal.map(cable => 
                                `<span class="cable-badge cable-para-terminal">${cable}</span>`
                            ).join('')}
                        </div>
                    </div>
                ` : ''}
                
                ${cablesAmbos.length > 0 ? `
                    <div class="terminal-group terminal-group-rojo">
                        <div class="terminal-group-header">
                            <span class="terminal-group-icon">🔗</span>
                            <span class="terminal-group-title">Ambos Lados</span>
                            <span class="terminal-group-count">${cablesAmbos.length}</span>
                        </div>
                        <div class="terminal-group-cables">
                            ${cablesAmbos.map(cable => 
                                `<span class="cable-badge cable-ambos-lados">${cable}</span>`
                            ).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>
        </div>
    `;
    
    document.getElementById('caja-expandida-contenido').innerHTML = `
        <div class="terminal-badge-caja-expandida">🔌 TERMINAL: ${terminalActual}</div>
        
        <div class="caja-expandida-header">
            <h2>Grupo ${index + 1} de ${gruposActuales.length}</h2>
            <div class="elemento-grande">${grupo.elemento}</div>
            <div class="codigo-cable-grande">Cable: ${grupo.cod_cable}</div>
        </div>
        
        <div class="caja-expandida-info">
            <span><strong>Total Cables:</strong> ${grupo.num_cables}</span>
            <span><strong>Total Terminales:</strong> ${grupo.num_terminales}</span>
            <span><strong>Sección:</strong> ${grupo.seccion || 'N/A'}</span>
        </div>
        
        ${seccionTerminales}
        
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
            esperarEnter(cajaIndex);
        }
    }, 1000);
}

/**
 * Esperar que el usuario pulse Enter para continuar
 */
function esperarEnter(cajaIndex) {
    const timerContainer = document.querySelector('.timer-container');
    
    // Cambiar apariencia del timer a "completado"
    timerContainer.innerHTML = `
        <div class="timer-completado">
            <div class="icono-completado">✅</div>
            <div class="mensaje-completado">¡Engastado completado!</div>
            <div class="instruccion-enter">Pulsa <strong>ENTER</strong> para continuar</div>
        </div>
    `;
    
    // Listener para Enter (guardarlo globalmente para poder limpiarlo)
    enterHandler = (e) => {
        if (e.key === 'Enter') {
            limpiarEnterHandler();
            esperandoEnterParaSiguiente = false; // Desactivar flag antes de completar
            completarCaja(cajaIndex);
        }
    };
    
    document.addEventListener('keypress', enterHandler);
    
    // Auto-focus para capturar Enter
    document.body.focus();
}

// Función para limpiar el listener de Enter
function limpiarEnterHandler() {
    if (enterHandler) {
        document.removeEventListener('keypress', enterHandler);
        enterHandler = null;
    }
}

/**
 * Activar listener de Enter para abrir la siguiente caja
 */
function activarEnterParaSiguienteCaja(index) {
    esperandoEnterParaSiguiente = true;
    
    // Crear handler de Enter para abrir la siguiente caja
    enterHandler = (e) => {
        if (e.key === 'Enter' && esperandoEnterParaSiguiente) {
            limpiarEnterHandler();
            esperandoEnterParaSiguiente = false;
            mostrarCajaExpandida(index);
        }
    };
    
    document.addEventListener('keypress', enterHandler);
    document.body.focus();
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
    
    // Guardar progreso
    if (!progresoGuardado[terminalActual]) {
        progresoGuardado[terminalActual] = {
            cajasCompletadas: [],
            siguienteCaja: 0
        };
    }
    
    if (!progresoGuardado[terminalActual].cajasCompletadas.includes(index)) {
        progresoGuardado[terminalActual].cajasCompletadas.push(index);
    }
    
    // Actualizar contador
    const completadas = progresoGuardado[terminalActual].cajasCompletadas.length;
    document.getElementById('grupos-completados').textContent = completadas;
    
    // Verificar si hay más cajas
    if (index + 1 < gruposActuales.length) {
        // Habilitar siguiente caja
        cajaActualIndex = index + 1;
        progresoGuardado[terminalActual].siguienteCaja = cajaActualIndex;
        habilitarCaja(cajaActualIndex);
        mostrarMensaje('✅ Caja completada. Pulsa ENTER para continuar con la siguiente', 'success');
        
        // Activar listener de Enter para abrir la siguiente caja (con pequeño delay)
        setTimeout(() => {
            activarEnterParaSiguienteCaja(cajaActualIndex);
        }, 100);
    } else {
        // Todas las cajas completadas
        progresoGuardado[terminalActual].siguienteCaja = gruposActuales.length;
        mostrarFinalizacion();
    }
}

/**
 * Volver a la selección de terminales guardando el progreso
 */
function volverASeleccionTerminales() {
    // Limpiar timer si está activo
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    
    // Limpiar listener de Enter si existe
    limpiarEnterHandler();
    esperandoEnterParaSiguiente = false;
    
    // Ocultar pantallas actuales
    document.getElementById('modo-engastado').classList.add('hidden');
    document.getElementById('caja-expandida').classList.add('hidden');
    document.getElementById('preparacion-paquetes').classList.add('hidden');
    
    // Resetear terminal actual pero mantener progreso guardado
    terminalActual = null;
    gruposActuales = [];
    cajaActualIndex = -1;
    
    // Volver a mostrar selección de terminales
    cargarListaTerminales();
}

/**
 * Mostrar pantalla de finalización
 */
function mostrarFinalizacion() {
    document.getElementById('modo-engastado').classList.add('hidden');
    document.getElementById('finalizacion').classList.remove('hidden');
    document.getElementById('terminal-finalizado').textContent = terminalActual;
    document.getElementById('total-completados').textContent = gruposActuales.length;
}

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
