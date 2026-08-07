// v3-paquetes-modal.js — Modal de paquetes del carro: bloqueos, saltos y confirmación.
// Parte del antiguo main-v3.js (troceado sin cambios de código).
// Los ficheros v3-*.js comparten el ámbito global y se cargan en orden desde index-v3.html.

// ========================================
// NUEVAS FUNCIONES PARA TRABAJO CON BONOS
// ========================================

/**
 * Cargar paquetes del carro actual para el terminal actual
 */
async function cargarPaquetesDelCarro() {
    if (carroActualIndex >= carrosDelBono.length) {
        // Terminamos todos los carros para este terminal
        terminarTerminal();
        return;
    }
    
    const carro = carrosDelBono[carroActualIndex];
    
    try {
        // Obtener datos del archivo Excel e iniciar sesión de trabajo (bloqueo concurrente)
        const response = await fetch(`/api/datos_trabajo_v3?archivo=${encodeURIComponent(carro.archivo_excel)}&terminal=${encodeURIComponent(terminalActual)}&maquina=${maquinaSeleccionada.id}&iniciar_sesion=true`);
        const data = await response.json();
        
        if (!data.success) {
            console.error('Error del servidor:', data.message || 'Sin mensaje');
            console.error('Datos completos:', data);
            mostrarMensaje(data.message || 'Error al cargar datos del carro', 'error');
            return;
        }
        
        if (!data.paquetes || data.paquetes.length === 0) {
            // Este carro no tiene datos para este terminal
            mostrarMensaje(`El carro ${carro.carro} no tiene trabajo para el terminal ${terminalActual}`, 'info');
            setTimeout(() => mostrarSeleccionCarro(), 1500);
            return;
        }
        
        paquetesActuales = data.paquetes;
        // Guardar ID de sesión para el bloqueo concurrente
        if (data.sesion_id) sesionActualId = data.sesion_id;

        // Si el carro tiene paquetes pendientes guardados, cargar solo esos
        const progresoTerminal = window.progresoCompleto?.[terminalActual];
        const pendientesGuardados = progresoTerminal?.carros_con_pendientes?.[String(carro.carro)]?.paquetes;
        if (pendientesGuardados && pendientesGuardados.length > 0) {
            const paquetesFiltrados = data.paquetes.filter(p =>
                pendientesGuardados.some(pe => pe.elemento === p.elemento && pe.cod_cable === p.cod_cable)
            );
            paquetesActuales = paquetesFiltrados.length > 0 ? paquetesFiltrados : data.paquetes;
            mostrarMensaje(`⚠️ Cargando ${paquetesActuales.length} paquete${paquetesActuales.length>1?'s':''} pendiente${paquetesActuales.length>1?'s':''} del carro ${carro.carro}`, 'warning');
        }

        paginaPaquetes = 0;    // reset al cargar nuevo carro
        batchFinIndex = 0;     // reset límite de lote
        paqueteActualIndex = 0; // reset índice para evitar falsos "completados" al cancelar
        paquetesOrdenados = []; // forzar re-orden
        paquetesSaltados = []; // reset saltados
        
        // Mostrar modal de confirmación de paquetes
        await mostrarModalPaquetes(carro);
        
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al cargar paquetes', 'error');
    }
}

/**
 * Mostrar modal con paquetes a coger del carro (paginado de 5 en 5)
 */
async function mostrarModalPaquetes(carro) {
    const gruposEtiquetas = await cargarGruposEtiquetas();

    // Ordenar y cachear los paquetes la primera vez
    if (paginaPaquetes === 0) {
        paquetesOrdenados = paquetesActuales.map(p => ({
            ...p,
            numeroEtiqueta: obtenerNumeroEtiqueta(p.cod_cable, p.elemento, gruposEtiquetas, p.archivo_excel)
        }));
        paquetesOrdenados.sort((a, b) => {
            if (a.numeroEtiqueta !== null && b.numeroEtiqueta !== null) return a.numeroEtiqueta - b.numeroEtiqueta;
            if (a.numeroEtiqueta !== null) return -1;
            if (b.numeroEtiqueta !== null) return 1;
            return a.elemento.localeCompare(b.elemento);
        });
    }

    const total = paquetesOrdenados.length;
    const inicio = paginaPaquetes * PAQUETES_POR_PAGINA;
    const fin = Math.min(inicio + PAQUETES_POR_PAGINA, total);
    let paginaActual = paquetesOrdenados.slice(inicio, fin);
    const esUltimaPagina = fin >= total;

    // Push a pantalla ESP32 (asíncrono, no bloquea el modal)
    pushToESP32({
        bono:  bonoActual?.nombre  || '',
        carro: carro.carro         || '',
        orden: carro.proyecto_nombre || '',
        paquetes: paginaActual.map(p => ({
            etiqueta: p.numeroEtiqueta ?? null,
            cod:  p.cod_cable  || '',
            elem: p.elemento   || '',
            bloqueado: !!p.bloqueado
        }))
    });

    // ---------------------------------------------------------------
    // Bloqueo anti-carrera: registrar claim ANTES de renderizar el modal,
    // luego re-verificar por si otro puesto nos ganó milisegundos antes.
    // Así el operario ve el paquete bloqueado antes de ir a buscarlo.
    // ---------------------------------------------------------------
    if (sesionActualId) {
        const paquetesLote = paginaActual
            .filter(p => !p.bloqueado)
            .map(p => ({ cod_cable: p.cod_cable, elemento: p.elemento }));

        if (paquetesLote.length > 0) {
            try {
                // 1. Registrar nuestro claim en la sesión
                await fetch('/api/sesion/actualizar-paquetes', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sesion_id: sesionActualId, paquetes: paquetesLote })
                });

                // 2. Re-verificar: ¿alguno fue reclamado por otra sesión antes que nosotros?
                const rv = await fetch('/api/sesion/verificar-pendientes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ paquetes: paquetesLote, sesion_id_excluir: sesionActualId })
                });
                const rvData = await rv.json();
                if (rvData.success && rvData.num_bloqueados > 0) {
                    // Marcar en paginaActual los que otro puesto ya reclamó
                    const ahora_bloqueados = new Map(
                        rvData.bloqueados.map(p => [`${p.cod_cable}||${p.elemento}`,
                            { bloqueado_por: p.bloqueado_por || 'otro puesto', bloqueado_terminal: p.bloqueado_terminal || '' }])
                    );
                    paginaActual = paginaActual.map(p => {
                        const info = ahora_bloqueados.get(`${p.cod_cable}||${p.elemento}`);
                        if (info) return { ...p, bloqueado: true, bloqueado_por: info.bloqueado_por, bloqueado_terminal: info.bloqueado_terminal };
                        return p;
                    });
                    // Propagar al array global para que la sesión no los tenga en cuenta
                    paginaActual.forEach((p, i) => { paquetesOrdenados[inicio + i] = p; });
                }
            } catch (e) { /* silencioso */ }
        }
    }
    const totalPaginas = Math.ceil(total / PAQUETES_POR_PAGINA);
    const paginaNum = paginaPaquetes + 1;

    // Calcular totales globales
    let totalCables = 0, totalTerminales = 0;
    paquetesActuales.forEach(p => {
        totalCables += p.num_cables || 0;
        totalTerminales += p.num_terminales || 0;
    });

    // Quitar modal anterior si existe
    const anterior = document.getElementById('modal-paquetes');
    if (anterior) anterior.remove();
    // Quitar listener Enter anterior
    if (window._confirmarEnterHandler) {
        document.removeEventListener('keypress', window._confirmarEnterHandler);
        window._confirmarEnterHandler = null;
    }

    // Resetear selección de paquetes no disponibles para esta página
    window._skipModal = new Set();

    // Calcular paquetes libres y bloqueados en la página actual
    const libresEnPagina = paginaActual.filter(p => !p.bloqueado).length;
    const bloqueadosEnPagina = paginaActual.filter(p => p.bloqueado).length;

    const modal = document.createElement('div');
    modal.id = 'modal-paquetes';
    modal.style.cssText = `position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);display:flex;justify-content:center;align-items:center;z-index:10000;`;

    modal.innerHTML = `
        <div style="background:white;border-radius:15px;padding:18px 20px;max-width:700px;width:95%;max-height:95vh;overflow-y:auto;">
            <div style="display:flex;gap:10px;margin-bottom:12px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:10px 14px;border-radius:10px;color:white;align-items:center;flex-wrap:wrap;">
                ${terminalImagenActual ? `
                <img src="${terminalImagenActual}" onclick="ampliarImagenTerminal(event)" title="Pulsa para ampliar" style="width:52px;height:52px;object-fit:contain;border-radius:8px;border:2px solid rgba(255,255,255,0.6);background:white;cursor:zoom-in;flex-shrink:0;" alt="Terminal ${terminalActual}">` : ''}
                <div style="flex:1;text-align:center;"><div style="font-size:1.2em;font-weight:bold;">${terminalActual}</div><div style="font-size:0.78em;opacity:0.9;">Terminal</div>${terminalGavetaActual ? `<div style="margin-top:3px;display:inline-block;background:rgba(255,255,255,0.25);padding:2px 8px;border-radius:10px;font-size:0.8em;font-weight:bold;">📍 ${terminalGavetaActual}</div>` : ''}</div>
                <div style="flex:1;text-align:center;"><div style="font-size:1.2em;font-weight:bold;">${total}</div><div style="font-size:0.78em;opacity:0.9;">Paquetes total</div></div>
                <div style="flex:1;text-align:center;"><div style="font-size:1.2em;font-weight:bold;">${totalCables}</div><div style="font-size:0.78em;opacity:0.9;">Cables</div></div>
                <div style="flex:1;text-align:center;"><div style="font-size:1.2em;font-weight:bold;">${totalTerminales}</div><div style="font-size:0.78em;opacity:0.9;">Terminales</div></div>
                <div style="flex:1;text-align:center;"><div style="font-size:1.2em;font-weight:bold;">Carro ${carro.carro}</div><div style="font-size:0.78em;opacity:0.9;">${carro.proyecto_nombre || ''}</div></div>
            </div>

            ${total > PAQUETES_POR_PAGINA ? `
            <div style="display:flex;align-items:center;justify-content:space-between;background:#e7f1ff;border-radius:8px;padding:10px 16px;margin-bottom:16px;">
                <span style="font-weight:600;color:#0d6efd;">Grupo ${paginaNum} de ${totalPaginas}</span>
                <span style="color:#495057;">Paquetes ${inicio+1}–${fin} de ${total}</span>
                <div style="display:flex;gap:4px;">${Array.from({length:totalPaginas},(_,i)=>`<div style="width:10px;height:10px;border-radius:50%;background:${i===paginaPaquetes?'#0d6efd':'#dee2e6'};"></div>`).join('')}</div>
            </div>` : ''}

            <div style="margin-bottom:20px;">
                <h3 style="margin-bottom:4px;font-size:1em;">📦 ${total > PAQUETES_POR_PAGINA ? `Paquetes ${inicio+1}–${fin} (grupo ${paginaNum}/${totalPaginas}):` : 'Paquetes a coger:'}</h3>
                ${libresEnPagina > 0 ? '<p style="font-size:0.78em;color:#6c757d;margin-bottom:6px;">👆 Pulsa en un paquete que <strong>no tengas</strong> para saltarlo al inicio</p>' : ''}
                ${bloqueadosEnPagina > 0 ? `<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:10px 14px;margin-bottom:12px;display:flex;gap:8px;align-items:center;font-size:0.88em;"><span>⚠️</span><span><strong>${bloqueadosEnPagina} paquete${bloqueadosEnPagina>1?'s están siendo trabajados':'  está siendo trabajado'} por otro puesto.</strong> Se saltarán automáticamente y quedarán pendientes.</span></div>` : ''}
                ${paginaActual.map((paquete, i) => { const _c = paquete.numeroEtiqueta ? getCodCableColor(paquete.cod_cable) : null; return paquete.bloqueado ? `
                <div style="background:#f1f3f5;border-left:4px solid #adb5bd;border-radius:8px;padding:14px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;opacity:0.6;cursor:not-allowed;">
                    <div style="display:flex;align-items:center;gap:14px;flex:1;">
                        <span style="min-width:68px;text-align:center;background:#adb5bd;color:white;padding:10px 12px;border-radius:10px;font-size:1.3em;">🔒</span>
                        <div>
                            <div style="font-size:1.2em;font-weight:bold;color:#6c757d;">${paquete.elemento}</div>
                            <div style="color:#adb5bd;font-size:0.82em;">En uso: ${paquete.bloqueado_por || 'otro puesto'}</div>
                        </div>
                    </div>
                    <div style="display:flex;gap:10px;align-items:flex-end;">
                        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
                            <div style="font-size:1.4em;font-weight:bold;color:#adb5bd;">${paquete.num_cables}</div>
                            <div style="font-size:0.82em;color:#adb5bd;">cables</div>
                        </div>
                        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
                            <div style="font-size:1.4em;font-weight:bold;color:#adb5bd;">${paquete.num_terminales || 0}</div>
                            <div style="font-size:0.82em;color:#adb5bd;">term.</div>
                        </div>
                    </div>
                </div>` : `
                <div id="pkg-row-${inicio+i}" onclick="toggleSkipModal(${inicio+i})" title="Pulsa para marcar como no disponible" style="background:#f8f9fa;border-left:4px solid ${_c?_c.bg:'#0d6efd'};border-radius:8px;padding:8px 10px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;transition:opacity 0.2s;">
                    <div style="display:flex;align-items:center;gap:10px;flex:1;">
                        ${paquete.numeroEtiqueta
                            ? `<span style="min-width:54px;text-align:center;background:${_c.bg};color:${_c.text};padding:5px 8px;border-radius:8px;font-weight:bold;font-size:1.05em;box-shadow:0 2px 4px rgba(0,0,0,0.15);">🏷️ ${paquete.numeroEtiqueta}</span>`
                            : `<span style="min-width:54px;text-align:center;background:#e9ecef;color:#6c757d;padding:5px 8px;border-radius:8px;font-size:0.85em;">Sin nº</span>`
                        }
                        <div>
                            <div style="font-size:1.05em;font-weight:bold;color:#212529;">${paquete.elemento}</div>
                            <div style="color:#6c757d;font-size:0.78em;">Paquete ${inicio+i+1} de ${total}</div>
                            <div id="pkg-no-${inicio+i}" style="display:none;color:#dc3545;font-size:0.75em;font-weight:600;margin-top:1px;">✕ No lo tengo — se saltará</div>
                        </div>
                    </div>
                    <div style="display:flex;gap:10px;align-items:flex-end;">
                        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px;">
                            <div style="font-size:1.2em;font-weight:bold;color:#0d6efd;">${paquete.num_cables}</div>
                            <div style="font-size:0.78em;color:#6c757d;">cables</div>
                        </div>
                        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px;">
                            <div style="font-size:1.2em;font-weight:bold;color:#e67e22;">${paquete.num_terminales || 0}</div>
                            <div style="font-size:0.78em;color:#6c757d;">term.</div>
                        </div>
                    </div>
                </div>`; }).join('')}
            </div>

            <div style="text-align:center;border-top:2px solid #dee2e6;padding-top:10px;">
                <p style="font-size:1em;color:#0d6efd;margin-bottom:10px;font-weight:bold;">
                    ${total > PAQUETES_POR_PAGINA
                        ? `Grupo ${paginaNum}/${totalPaginas}: pon ${libresEnPagina} paquete${libresEnPagina!==1?'s':''} en tu zona.${fin >= total ? ' (¡último grupo!)' : ` Quedan ${total - fin} más en el siguiente grupo.`}`
                        : libresEnPagina > 0 ? `Pon estos ${libresEnPagina} paquete${libresEnPagina!==1?'s':''} en tu zona de trabajo.` : 'Todos los paquetes de esta página están en uso por otro puesto.'
                    }
                </p>
                <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
                    <button onclick="cancelarModalPaquetes()" style="padding:12px 24px;font-size:1em;background:#6c757d;color:white;border:none;border-radius:8px;cursor:pointer;">&#10060; Cancelar</button>
                    <button id="btn-confirmar-paquetes" onclick="confirmarPaginaPaquetes()" style="padding:12px 32px;font-size:1.1em;background:${libresEnPagina === 0 ? '#6c757d' : '#0d6efd'};color:white;border:none;border-radius:8px;cursor:pointer;font-weight:bold;">
                        ${libresEnPagina === 0 ? '⏭️ Continuar (todo en uso) →' : libresEnPagina > 1 ? `✅ Tengo estos ${libresEnPagina}, empezar →` : '✅ Tengo este paquete, empezar →'}
                    </button>
                </div>
                ${bloqueadosEnPagina > 0 ? `<p id="bloqueos-estado" style="margin-top:12px;color:#6c757d;font-size:0.88em;">⏳ Comprobando si se liberan paquetes bloqueados...</p>` : `<p style="margin-top:12px;color:#6c757d;font-size:0.88em;">💡 Pulsa <strong>Enter</strong> para confirmar.</p>`}
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    window._confirmarEnterHandler = (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.removeEventListener('keypress', window._confirmarEnterHandler);
            window._confirmarEnterHandler = null;
            confirmarPaginaPaquetes();
        }
    };
    document.addEventListener('keypress', window._confirmarEnterHandler);

    // Auto-refresh de bloqueos cada 5s si hay paquetes bloqueados en esta página
    if (bloqueadosEnPagina > 0) {
        if (window._bloqueoInterval) clearInterval(window._bloqueoInterval);
        window._bloqueoInterval = setInterval(() => actualizarBloqueos(), 5000);
    }
}

/**
 * Auto-refresh de bloqueos: consulta verificar-pendientes con los paquetes
 * bloqueados de la página actual y re-renderiza el modal si algo cambió.
 */
async function actualizarBloqueos() {
    // Si el modal ya no existe, detener el intervalo
    if (!document.getElementById('modal-paquetes')) {
        clearInterval(window._bloqueoInterval);
        window._bloqueoInterval = null;
        return;
    }
    try {
        const bloqueadosActuales = paginaActual.filter(p => p.bloqueado);
        if (!bloqueadosActuales.length) {
            clearInterval(window._bloqueoInterval);
            window._bloqueoInterval = null;
            return;
        }
        const r = await fetch('/api/sesion/verificar-pendientes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                paquetes: bloqueadosActuales.map(p => ({ cod_cable: p.cod_cable, elemento: p.elemento })),
                sesion_id_excluir: sesionActualId || null
            })
        });
        const data = await r.json();
        if (!data.libres || data.libres.length === 0) {
            // Nada cambió — actualizar texto del estado
            const el = document.getElementById('bloqueos-estado');
            if (el) el.textContent = `⏳ Esperando que se liberen ${data.num_bloqueados} paquete${data.num_bloqueados !== 1 ? 's' : ''}... (se comprueba cada 5s)`;
            return;
        }
        // Hay paquetes liberados — actualizar paginaActual y re-renderizar
        const libresSet = new Set(data.libres.map(p => `${p.cod_cable}||${p.elemento}`));
        paginaActual = paginaActual.map(p =>
            libresSet.has(`${p.cod_cable}||${p.elemento}`) ? { ...p, bloqueado: false, bloqueado_por: null } : p
        );
        // Sincronizar también en paquetesOrdenados
        paquetesOrdenados = paquetesOrdenados.map(p =>
            libresSet.has(`${p.cod_cable}||${p.elemento}`) ? { ...p, bloqueado: false, bloqueado_por: null } : p
        );
        clearInterval(window._bloqueoInterval);
        window._bloqueoInterval = null;
        // Re-renderizar el modal
        const carro = carrosDelBono[carroActualIndex];
        await mostrarModalPaquetes(carro);
    } catch (e) {
        // Error de red — reintentar en el siguiente tick del intervalo
    }
}

/**
 * Confirmar página de paquetes: avanzar a siguiente grupo o comenzar trabajo
 */
/**
 * Alternar un paquete del modal como "no lo tengo" (se saltará al comenzar)
 */
function toggleSkipModal(idx) {
    if (!window._skipModal) window._skipModal = new Set();
    if (window._skipModal.has(idx)) {
        window._skipModal.delete(idx);
    } else {
        window._skipModal.add(idx);
    }
    const row = document.getElementById(`pkg-row-${idx}`);
    const badge = document.getElementById(`pkg-no-${idx}`);
    const skipped = window._skipModal.has(idx);
    if (row) {
        row.style.opacity = skipped ? '0.45' : '1';
        row.style.textDecoration = skipped ? 'line-through' : '';
        row.style.background = skipped ? '#f1f3f5' : '#f8f9fa';
    }
    if (badge) badge.style.display = skipped ? 'block' : 'none';
    _actualizarBotonConfirmarModal();
}

/**
 * Actualizar el texto del botón de confirmación según cuántos paquetes están activos
 */
function _actualizarBotonConfirmarModal() {
    const btn = document.getElementById('btn-confirmar-paquetes');
    if (!btn) return;
    const inicio = paginaPaquetes * PAQUETES_POR_PAGINA;
    const fin = Math.min(inicio + PAQUETES_POR_PAGINA, paquetesOrdenados.length);
    // Excluir paquetes bloqueados del conteo (no se pueden trabajar)
    const bloqueadosEnLote = paquetesOrdenados.slice(inicio, fin).filter(p => p.bloqueado).length;
    const totalPagina = fin - inicio - bloqueadosEnLote;
    const skipped = window._skipModal ? window._skipModal.size : 0;
    const activos = totalPagina - skipped;
    if (activos <= 0) {
        btn.textContent = bloqueadosEnLote > 0 ? '⏭️ Continuar (todo en uso) →' : '⏭️ Saltar todos e ir al siguiente →';
        btn.style.background = '#6c757d';
    } else if (skipped > 0) {
        btn.textContent = `✅ Tengo ${activos} de ${totalPagina}, empezar →`;
        btn.style.background = '#0d6efd';
    } else {
        btn.textContent = activos > 1 ? `✅ Tengo estos ${activos}, empezar →` : '✅ Tengo este paquete, empezar →';
        btn.style.background = '#0d6efd';
    }
}

function confirmarPaginaPaquetes() {
    const modal = document.getElementById('modal-paquetes');
    if (modal) modal.remove();
    if (window._confirmarEnterHandler) {
        document.removeEventListener('keypress', window._confirmarEnterHandler);
        window._confirmarEnterHandler = null;
    }
    // Pre-saltar los paquetes que el usuario marcó como no disponibles
    if (window._skipModal && window._skipModal.size > 0) {
        const inicio = paginaPaquetes * PAQUETES_POR_PAGINA;
        const fin = Math.min(inicio + PAQUETES_POR_PAGINA, paquetesOrdenados.length);
        for (const idx of window._skipModal) {
            if (idx >= inicio && idx < fin) {
                const p = paquetesOrdenados[idx];
                paquetesSaltados.push({
                    elemento: p.elemento,
                    cod_cable: p.cod_cable,
                    num_cables: p.num_cables,
                    indice: idx,
                    pre_saltado: true
                });
                // Liberar el paquete de nuestra sesión para que otro puesto pueda cogerlo
                if (!p.bloqueado && sesionActualId) {
                    fetch('/api/sesion/liberar-paquete', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ sesion_id: sesionActualId, cod_cable: p.cod_cable, elemento: p.elemento })
                    }).catch(() => {});
                }
            }
        }
        // Guardar los índices pre-saltados para que mostrarPaqueteExpandido los salte
        window._preSkipModal = new Set(window._skipModal);
        window._skipModal.clear();
    } else {
        window._preSkipModal = new Set();
    }
    // Iniciar trabajo en el lote actual
    const inicio = paginaPaquetes * PAQUETES_POR_PAGINA;
    paqueteActualIndex = inicio;
    batchFinIndex = Math.min(inicio + PAQUETES_POR_PAGINA, paquetesOrdenados.length);
    mostrarPaqueteExpandido();
}

/**
 * Obtener color de fondo para badge de cable
 */
function getColorCable(color) {
    const colores = {
        'Verde': '#28a745',
        'Azul': '#007bff',
        'Rojo': '#dc3545',
        'Gris': '#6c757d',
        'Amarillo': '#ffc107',
        'Naranja': '#fd7e14',
        'Blanco': '#e9ecef',
        'Negro': '#212529'
    };
    return colores[color] || '#6c757d';
}

/**
 * Cerrar modal de paquetes
 */
function cerrarModalPaquetes() {
    const modal = document.getElementById('modal-paquetes');
    if (modal) modal.remove();
    // Solo cierra el modal, el flujo continua con confirmarPaquetesYComenzar
}

/**
 * Ampliar la foto del terminal en un lightbox (para verlo bien ante dudas)
 */
function ampliarImagenTerminal(event) {
    if (event) event.stopPropagation();
    if (!terminalImagenActual) return;

    const anterior = document.getElementById('modal-imagen-terminal');
    if (anterior) anterior.remove();

    const overlay = document.createElement('div');
    overlay.id = 'modal-imagen-terminal';
    overlay.style.cssText = `position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.9);display:flex;flex-direction:column;justify-content:center;align-items:center;z-index:11000;cursor:zoom-out;padding:20px;box-sizing:border-box;`;
    overlay.innerHTML = `
        <div style="color:white;font-size:1.3em;font-weight:bold;margin-bottom:12px;">📸 ${terminalActual}</div>
        <img src="${terminalImagenActual}" style="max-width:90%;max-height:78vh;object-fit:contain;border-radius:12px;background:white;box-shadow:0 8px 40px rgba(0,0,0,0.5);" alt="Terminal ${terminalActual}">
        <div style="color:rgba(255,255,255,0.8);font-size:0.9em;margin-top:14px;">Pulsa en cualquier sitio o <strong>Esc</strong> para cerrar</div>
    `;
    overlay.addEventListener('click', cerrarImagenTerminal);
    document.body.appendChild(overlay);

    window._imgTerminalEscHandler = (e) => { if (e.key === 'Escape') cerrarImagenTerminal(); };
    document.addEventListener('keydown', window._imgTerminalEscHandler);
}

function cerrarImagenTerminal() {
    const overlay = document.getElementById('modal-imagen-terminal');
    if (overlay) overlay.remove();
    if (window._imgTerminalEscHandler) {
        document.removeEventListener('keydown', window._imgTerminalEscHandler);
        window._imgTerminalEscHandler = null;
    }
}

async function cancelarModalPaquetes() {
    // Volver al panel ESP32 (limpiar pantalla de trabajo)
    pushToESP32({ clear: true });
    // Detener auto-refresh de bloqueos
    if (window._bloqueoInterval) {
        clearInterval(window._bloqueoInterval);
        window._bloqueoInterval = null;
    }
    const modal = document.getElementById('modal-paquetes');
    if (modal) modal.remove();
    if (window._confirmarEnterHandler) {
        document.removeEventListener('keypress', window._confirmarEnterHandler);
        window._confirmarEnterHandler = null;
    }
    // Limpiar _skipModal sin procesar (el usuario canceló antes de confirmar)
    if (window._skipModal) window._skipModal.clear();

    // --- Calcular TODOS los paquetes realmente pendientes ---
    // 1. Los ya registrados como saltados durante el trabajo (pre-salto + saltar durante engaste)
    const indicesSaltadosRegistrados = new Set(paquetesSaltados.map(p => p.indice));
    // 2. Paquetes no iniciados: desde paqueteActualIndex hasta el final
    const pendientesNoIniciados = paquetesOrdenados
        .slice(paqueteActualIndex)
        .map((p, i) => ({ elemento: p.elemento, cod_cable: p.cod_cable, num_cables: p.num_cables, indice: paqueteActualIndex + i }))
        .filter(p => !indicesSaltadosRegistrados.has(p.indice));

    const todosPendientes = [
        ...paquetesSaltados.map(p => ({ elemento: p.elemento, cod_cable: p.cod_cable, num_cables: p.num_cables, bloqueado: !!p.bloqueado })),
        ...pendientesNoIniciados.map(p => ({ elemento: p.elemento, cod_cable: p.cod_cable, num_cables: p.num_cables, bloqueado: false }))
    ];

    // Paquetes realmente hechos = paqueteActualIndex menos los pre-saltados anteriores a ese índice
    const paquetesRealmenteHechos = paqueteActualIndex - paquetesSaltados.filter(p => p.indice < paqueteActualIndex).length;

    const hayProgreso = paquetesRealmenteHechos > 0 || todosPendientes.length > 0;
    if (hayProgreso && bonoActual && carrosDelBono[carroActualIndex]) {
        const carro = carrosDelBono[carroActualIndex];
        try {
            await fetch(`/api/bonos/${bonoActual.nombre}/progreso/parcial`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    terminal: terminalActual,
                    carro: carro.carro,
                    operario: operarioActual || '',
                    paquetes_hechos: paquetesRealmenteHechos,
                    paquetes_saltados: paquetesSaltados.map(p => ({ elemento: p.elemento, cod_cable: p.cod_cable, num_cables: p.num_cables })),
                    paquetes_pendientes: todosPendientes
                })
            });
            const msg = todosPendientes.length > 0
                ? `⚠️ Cancelado. ${paquetesRealmenteHechos} hechos, ${todosPendientes.length} pendiente${todosPendientes.length > 1 ? 's' : ''} guardados.`
                : `💾 Cancelado. Progreso (${paquetesRealmenteHechos} paquetes) guardado.`;
            mostrarMensaje(msg, 'warning');
        } catch (e) {
            console.error('Error guardando progreso parcial:', e);
        }
    }
    // Liberar sesión de trabajo al cancelar
    if (sesionActualId) {
        fetch('/api/sesion/liberar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sesion_id: sesionActualId })
        }).catch(() => {});
        sesionActualId = null;
    }
    document.getElementById('area-trabajo')?.classList.remove('fullscreen-engaste');
    const _me1 = document.getElementById('modal-engaste');
    if (_me1) _me1.remove();
    mostrarSeleccionCarro();
}

/**
 * Confirmar paquetes y comenzar trabajo
 */
let paqueteActualIndex = 0;
let handlerEnterPaquete = null; // Handler global para evitar duplicados
let paquetesOrdenados = [];    // Paquetes del carro ordenados por etiqueta
let paginaPaquetes = 0;        // Página actual (grupos de 5)
let batchFinIndex = 0;         // Índice límite del lote actual en la vista expandida
let paquetesSaltados = [];     // Paquetes saltados en este carro (pendientes)
const PAQUETES_POR_PAGINA = 5;

function saltarPaquete() {
    if (paqueteActualIndex >= paquetesOrdenados.length) return;
    const paquete = paquetesOrdenados[paqueteActualIndex];
    paquetesSaltados.push({
        elemento: paquete.elemento,
        cod_cable: paquete.cod_cable,
        num_cables: paquete.num_cables,
        indice: paqueteActualIndex
    });
    // Liberar el paquete de nuestra sesión para que otro puesto pueda cogerlo
    if (!paquete.bloqueado && sesionActualId) {
        fetch('/api/sesion/liberar-paquete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sesion_id: sesionActualId, cod_cable: paquete.cod_cable, elemento: paquete.elemento })
        }).catch(() => {});
    }
    if (handlerEnterPaquete) {
        document.removeEventListener('keypress', handlerEnterPaquete);
        handlerEnterPaquete = null;
    }
    paqueteActualIndex++;
    mostrarPaqueteExpandido();
}

function volverPaqueteAnterior() {
    if (paqueteActualIndex <= 0) return;
    if (handlerEnterPaquete) {
        document.removeEventListener('keypress', handlerEnterPaquete);
        handlerEnterPaquete = null;
    }
    window._confirmandoFinal = false;
    paqueteActualIndex--;
    // Si este paquete estaba marcado como saltado, quitarlo de la lista
    const idx = paquetesSaltados.findIndex(p => p.indice === paqueteActualIndex);
    if (idx !== -1) paquetesSaltados.splice(idx, 1);
    mostrarPaqueteExpandido();
}

function cancelarConfirmacionFinal() {
    window._confirmandoFinal = false;
    mostrarPaqueteExpandido();
}

function avanzarPaquete() {
    const esUltimo = paqueteActualIndex === paquetesOrdenados.length - 1;
    if (esUltimo && !window._confirmandoFinal) {
        window._confirmandoFinal = true;
        const footer = document.getElementById('footer-paquete');
        if (footer) {
            footer.innerHTML = `
                <div style="background:#fff3e0;border:2px solid #ff9800;border-radius:10px;padding:18px;text-align:center;">
                    <p style="font-size:1.25em;color:#e65100;font-weight:bold;margin-bottom:8px;">⚠️ ¿Seguro que has terminado el carro?</p>
                    <p style="color:#6c757d;font-size:0.9em;margin-bottom:16px;">Pulsa <strong>Confirmar</strong> o <strong>ENTER</strong> para guardar y cerrar</p>
                    <div style="display:flex;gap:10px;justify-content:center;">
                        <button onclick="cancelarConfirmacionFinal()" style="padding:10px 26px;font-size:0.95em;background:#e9ecef;color:#495057;border:2px solid #ced4da;border-radius:8px;cursor:pointer;font-weight:600;">◀ Volver</button>
                        <button onclick="avanzarPaquete()" style="padding:10px 26px;font-size:0.95em;background:#28a745;color:white;border:none;border-radius:8px;cursor:pointer;font-weight:700;">✅ Confirmar</button>
                    </div>
                </div>`;
        }
        return;
    }
    if (handlerEnterPaquete) {
        document.removeEventListener('keypress', handlerEnterPaquete);
        handlerEnterPaquete = null;
    }
    window._confirmandoFinal = false;
    if (esUltimo) {
        const me = document.getElementById('modal-engaste');
        if (me) me.innerHTML = `<div style="display:flex;justify-content:center;align-items:center;min-height:200px;"><div style="background:white;border-radius:16px;padding:50px 60px;text-align:center;"><div style="font-size:3em;margin-bottom:20px;">⏳</div><h2 style="color:#0d6efd;margin-bottom:15px;">Guardando progreso...</h2><div style="color:#6c757d;">Por favor espera un momento</div></div></div>`;
    }
    paqueteActualIndex++;
    mostrarPaqueteExpandido();
}

function _agregarSwipeModal() {
    const modal = document.getElementById('modal-engaste');
    if (!modal) return;
    let _tx = 0;
    const _onStart = (e) => { _tx = e.changedTouches[0].clientX; };
    const _onEnd = (e) => {
        const dx = e.changedTouches[0].clientX - _tx;
        if (Math.abs(dx) < 60) return;
        if (dx < 0 && !window._confirmandoFinal) avanzarPaquete();
        else if (dx > 0) volverPaqueteAnterior();
    };
    if (modal._swipeStart) modal.removeEventListener('touchstart', modal._swipeStart);
    if (modal._swipeEnd)   modal.removeEventListener('touchend',   modal._swipeEnd);
    modal._swipeStart = _onStart;
    modal._swipeEnd   = _onEnd;
    modal.addEventListener('touchstart', _onStart, { passive: true });
    modal.addEventListener('touchend',   _onEnd,   { passive: true });
}

function confirmarPaquetesYComenzar() {
    confirmarPaginaPaquetes();
}

/**
 * Mostrar paquete expandido con detalles de cables
 */
