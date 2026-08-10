// v3-paquete-expandido.js — Paquete expandido, completado de terminal y resúmenes finales.
// Parte del antiguo main-v3.js (troceado sin cambios de código).
// Los ficheros v3-*.js comparten el ámbito global y se cargan en orden desde index-v3.html.

async function mostrarPaqueteExpandido() {
    // Asegurar que no hay fullscreen residual
    document.getElementById('area-trabajo')?.classList.remove('fullscreen-engaste');

    if (paqueteActualIndex >= batchFinIndex) {
        if (batchFinIndex >= paquetesOrdenados.length) {
            paqueteCompletado();
        } else {
            paginaPaquetes++;
            mostrarModalPaquetes(carrosDelBono[carroActualIndex]);
        }
        return;
    }
    
    // Auto-saltar si este paquete fue marcado como no disponible en el modal
    if (window._preSkipModal && window._preSkipModal.has(paqueteActualIndex)) {
        window._preSkipModal.delete(paqueteActualIndex);
        paqueteActualIndex++;
        mostrarPaqueteExpandido();
        return;
    }

    const paquete = paquetesOrdenados[paqueteActualIndex];

    // Auto-saltar paquetes bloqueados por otro puesto (no son de nuestra sesión)
    if (paquete.bloqueado) {
        paquetesSaltados.push({
            elemento: paquete.elemento,
            cod_cable: paquete.cod_cable,
            num_cables: paquete.num_cables,
            indice: paqueteActualIndex,
            bloqueado: true
        });
        paqueteActualIndex++;
        mostrarPaqueteExpandido();
        return;
    }
    
    // Cargar grupos de etiquetas y obtener número
    const gruposEtiquetas = await cargarGruposEtiquetas();
    const numeroEtiqueta = obtenerNumeroEtiqueta(paquete.cod_cable, paquete.elemento, gruposEtiquetas, paquete.archivo_excel);
    const _etq = getCodCableColor(paquete.cod_cable);
    const etiquetaHtml = numeroEtiqueta 
        ? `<span style="display: inline-block; background: ${_etq.bg}; color: ${_etq.text}; padding: 10px 20px; border-radius: 10px; font-weight: bold; font-size: 1.2em; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">🏷️ #${numeroEtiqueta}</span>`
        : '';
    
    const cablesDeTerminal = paquete.cables_de_terminal || [];
    const cablesParaTerminal = paquete.cables_para_terminal || [];
    const cablesAmbos = paquete.cables_doble_terminal || [];

    const areaTrabajoV2 = document.getElementById('area-trabajo');

    // Crear o reutilizar overlay modal
    let modalEngaste = document.getElementById('modal-engaste');
    if (!modalEngaste) {
        modalEngaste = document.createElement('div');
        modalEngaste.id = 'modal-engaste';
        modalEngaste.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.75);display:flex;justify-content:center;align-items:center;z-index:10000;padding:16px;box-sizing:border-box;';
        document.body.appendChild(modalEngaste);
    }

    // ── Renderizado especial para paquetes de grupo serie SXX ──
    if (paquete.es_grupo) {
        const grupoSerie = paquete.grupo_serie;
        const gruposEtiquetas2 = await cargarGruposEtiquetas();
        const numPadre = (gruposEtiquetas2.find(g => g.es_grupo_padre && g.elemento === grupoSerie))?.numero_etiqueta ?? '';
        const etiquetaPadreHtml = numPadre
            ? `<span style="display:inline-block;background:#f59e0b;color:white;padding:10px 20px;border-radius:10px;font-weight:bold;font-size:1.2em;margin-bottom:10px;box-shadow:0 2px 4px rgba(0,0,0,0.2);">&#127991;&#65039; Etiqueta ${grupoSerie} — #${numPadre}</span>`
            : `<span style="display:inline-block;background:#6c757d;color:white;padding:8px 16px;border-radius:8px;font-weight:bold;font-size:1.1em;margin-bottom:10px;">&#128230; ${grupoSerie}</span>`;

        const subPaquetesHtml = (paquete.sub_paquetes || []).map((sub, i) => {
            const numSub = numPadre ? `${numPadre}.${String(sub.sub_numero || (i+1)).padStart(2, '0')}` : `${i+1}`;
            const _sub = getCodCableColor(sub.cod_cable);
            const cablesDe   = sub.cables_de_terminal   || [];
            const cablesPara = sub.cables_para_terminal || [];
            const cablesAmb  = sub.cables_doble_terminal|| [];
            const seccionesHtml = `
                ${cablesDe.length > 0 ? `
                <div style="background:linear-gradient(135deg,#e3f2fd 0%,#bbdefb 100%);border-left:5px solid #2196f3;padding:12px 15px;border-radius:10px;margin-top:8px;">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                        <span style="font-size:1.3em;">📍</span>
                        <span style="font-weight:bold;color:#1976d2;">De Terminal</span>
                        <span style="background:#2196f3;color:white;padding:2px 10px;border-radius:10px;font-size:0.9em;font-weight:bold;margin-left:auto;">${cablesDe.length}</span>
                    </div>
                    <div style="display:flex;flex-wrap:wrap;gap:6px;">
                        ${cablesDe.map(c => `<span style="background:#bbdefb;color:#0d2a4a;padding:7px 14px;border-radius:8px;font-weight:900;font-size:1em;border:1.5px solid #64b5f6;">${c}</span>`).join('')}
                    </div>
                    <div style="margin-top:8px;padding:6px 10px;background:rgba(33,150,243,0.12);border-radius:6px;display:flex;align-items:center;gap:6px;">
                        <span style="font-size:1em;">✅</span>
                        <span style="font-size:0.82em;color:#1565c0;font-style:italic;">Pon el terminal en el lado <strong>liso</strong> del cable (sin guion)</span>
                    </div>
                </div>` : ''}
                ${cablesPara.length > 0 ? `
                <div style="background:linear-gradient(135deg,#e8f5e9 0%,#c8e6c9 100%);border-left:5px solid #4caf50;padding:12px 15px;border-radius:10px;margin-top:8px;">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                        <span style="font-size:1.3em;">🎯</span>
                        <span style="font-weight:bold;color:#1b5e20;">Para Terminal</span>
                        <span style="background:#c8e6c9;color:#1b5e20;padding:2px 10px;border-radius:10px;font-size:0.9em;font-weight:bold;margin-left:auto;border:1.5px solid #81c784;">${cablesPara.length}</span>
                    </div>
                    <div style="display:flex;flex-wrap:wrap;gap:6px;">
                        ${cablesPara.map(c => `<span style="background:#c8e6c9;color:#1b5e20;padding:7px 14px;border-radius:8px;font-weight:900;font-size:1em;border:1.5px solid #81c784;">${c}</span>`).join('')}
                    </div>
                    <div style="margin-top:8px;padding:6px 10px;background:rgba(76,175,80,0.15);border-radius:6px;display:flex;align-items:center;gap:6px;">
                        <span style="font-size:1em;">✂️</span>
                        <span style="font-size:0.82em;color:#2e7d32;font-style:italic;">Pon el terminal en el lado del <strong>guion</strong> — la máquina de corte marca así todos los cables, ej: <strong>208-</strong></span>
                    </div>
                </div>` : ''}
                ${cablesAmb.length > 0 ? `
                <div style="background:linear-gradient(135deg,#ffebee 0%,#ffcdd2 100%);border-left:5px solid #f44336;padding:12px 15px;border-radius:10px;margin-top:8px;">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                        <span style="font-size:1.3em;">🔗</span>
                        <span style="font-weight:bold;color:#7f0000;">Ambos Lados</span>
                        <span style="background:#ffcdd2;color:#7f0000;padding:2px 10px;border-radius:10px;font-size:0.9em;font-weight:bold;margin-left:auto;border:1.5px solid #e57373;">${cablesAmb.length}</span>
                    </div>
                    <div style="display:flex;flex-wrap:wrap;gap:6px;">
                        ${cablesAmb.map(c => `<span style="background:#ffcdd2;color:#7f0000;padding:7px 14px;border-radius:8px;font-weight:900;font-size:1em;border:1.5px solid #e57373;">${c}</span>`).join('')}
                    </div>
                </div>` : ''}
                ${(!cablesDe.length && !cablesPara.length && !cablesAmb.length) ? '<span style="color:#6c757d;font-size:0.9em;">Sin cables clasificados</span>' : ''}
            `;
            return `
            <div style="padding:14px 0;border-bottom:1px solid #e9ecef;">
                <div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;">
                    <div style="background:${_sub.bg};color:${_sub.text};padding:8px 16px;border-radius:10px;border:2px dashed rgba(255,255,255,0.6);text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.15);min-width:54px;">
                        <div style="font-size:1.5em;font-weight:900;letter-spacing:1px;line-height:1;">${numSub}</div>
                    </div>
                    <span style="font-size:1.05em;font-weight:700;color:#212529;">${sub.elemento}</span>
                </div>
                ${seccionesHtml}
            </div>`;
        }).join('');

        modalEngaste.innerHTML = `
        <div style="background:white;border-radius:16px;overflow:hidden;box-shadow:0 8px 40px rgba(0,0,0,0.35);width:100%;max-width:975px;max-height:calc(100vh - 32px);display:flex;flex-direction:column;">

            <div style="background:#1e293b;color:white;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;gap:10px;flex-shrink:0;">
                <div style="display:flex;align-items:center;gap:12px;">
                    <div style="display:flex;flex-direction:column;align-items:center;">
                        <span style="font-size:0.7em;letter-spacing:1px;text-transform:uppercase;opacity:0.55;">Carro</span>
                        <div style="background:#f59e0b;color:#1e293b;padding:8px 22px;border-radius:8px;font-size:2.2em;font-weight:900;letter-spacing:1px;line-height:1;margin-top:2px;">🚗 ${carrosDelBono[carroActualIndex]?.carro ?? ''}</div>
                    </div>
                    <div style="font-size:0.95em;color:rgba(255,255,255,0.65);border-left:1px solid rgba(255,255,255,0.15);padding-left:14px;">${carrosDelBono[carroActualIndex]?.proyecto_nombre ?? ''}</div>
                </div>
                <div style="display:flex;align-items:center;gap:16px;">
                    <div style="text-align:right;">
                        <div style="font-size:0.7em;letter-spacing:1px;text-transform:uppercase;opacity:0.55;">Terminal</div>
                        <div style="font-size:1.25em;font-weight:700;margin-top:2px;">${terminalActual}</div>
                        <div style="font-size:0.8em;opacity:0.5;margin-top:1px;">${paqueteActualIndex + 1} / ${paquetesOrdenados.length}</div>
                    </div>
                    <button onclick="cancelarModalPaquetes()" title="Salir" style="background:rgba(255,255,255,0.12);border:1.5px solid rgba(255,255,255,0.25);color:white;border-radius:8px;width:40px;height:40px;font-size:1.2em;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;">&times;</button>
                </div>
            </div>

            <div id="engaste-scroll-body" style="flex:1;overflow-y:auto;padding:20px 24px 12px;">

            ${maquinaSeleccionada?.lleva_regulacion ? `
            <div onclick="verPdfRegulacionV3()" style="display:flex;align-items:center;gap:12px;background:#2d1b69;border:1.5px solid #a855f7;border-radius:10px;padding:11px 16px;margin-bottom:16px;cursor:${maquinaSeleccionada?.pdf_regulacion ? 'pointer' : 'default'};user-select:none;">
                <span style="font-size:1.5em;flex-shrink:0;">🔧</span>
                <div style="flex:1;">
                    <div style="font-size:0.82em;font-weight:700;color:#c4b5fd;letter-spacing:.04em;">ATENCI\u00d3N — M\u00c1QUINA CON REGULACI\u00d3N</div>
                    <div style="font-size:0.78em;color:rgba(196,181,253,.7);margin-top:2px;">${maquinaSeleccionada?.pdf_regulacion ? 'Toca para ver el PDF de regulaci\u00f3n' : 'Verifica que la regulaci\u00f3n es correcta antes de engastar'}</div>
                </div>
                ${maquinaSeleccionada?.pdf_regulacion ? '<span style="font-size:1.2em;opacity:.8;">\u2197\ufe0f</span>' : ''}
            </div>` : ''}

            <div style="text-align:center;margin-bottom:18px;">
                ${numPadre ? `
                <div style="display:inline-flex;flex-direction:column;align-items:center;background:#f59e0b;color:#111;padding:12px 34px;border-radius:12px;border:3px dashed rgba(0,0,0,0.25);box-shadow:0 4px 12px rgba(0,0,0,0.18);">
                    <span style="font-size:2.8em;font-weight:900;letter-spacing:2px;line-height:1;">${numPadre}</span>
                    <span style="font-size:0.9em;font-weight:700;margin-top:4px;">Serie ${grupoSerie}</span>
                </div>` : `<div style="display:inline-block;background:#6c757d;color:white;padding:10px 24px;border-radius:10px;font-weight:bold;font-size:1.3em;">Serie ${grupoSerie}</div>`}
            </div>

            <div style="display:grid;gap:10px;">
                ${subPaquetesHtml}
            </div>

            <div style="padding-top:20px;padding-bottom:6px;text-align:right;">
                ${paquetesSaltados.length > 0 ? `<div style="font-size:0.78em;color:#e67e22;margin-bottom:6px;">⚠️ ${paquetesSaltados.length} saltado${paquetesSaltados.length>1?'s':''}</div>` : ''}
                <button onclick="avanzarPaquete()" style="padding:14px 32px;font-size:1.05em;font-weight:700;background:#0d6efd;color:white;border:none;border-radius:10px;cursor:pointer;min-width:180px;touch-action:manipulation;">
                    ${paqueteActualIndex === paquetesOrdenados.length - 1 ? '✅ Finalizar carro' : paqueteActualIndex === batchFinIndex - 1 ? '⏭️ Siguiente grupo' : 'Siguiente ▶'}
                </button>
            </div>

            </div>

            <div id="footer-paquete" style="padding:12px 20px;border-top:1px solid #e9ecef;background:#f8f9fa;flex-shrink:0;">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;">
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        ${paqueteActualIndex > 0 ? `<button onclick="volverPaqueteAnterior()" style="padding:8px 16px;font-size:0.88em;background:white;color:#495057;border:1.5px solid #ced4da;border-radius:8px;cursor:pointer;font-weight:600;">◀ Anterior</button>` : ''}
                        <button onclick="saltarPaquete()" style="padding:8px 16px;font-size:0.88em;background:#fff3cd;color:#856404;border:1.5px solid #ffc107;border-radius:8px;cursor:pointer;font-weight:600;">⤵️ Saltar</button>
                    </div>
                    <button onclick="document.getElementById('engaste-scroll-body')?.scrollTo({top:99999,behavior:'smooth'})" style="padding:10px 22px;font-size:1em;font-weight:700;background:#1e293b;color:white;border:none;border-radius:8px;cursor:pointer;touch-action:manipulation;">↓ Bajar</button>
                </div>
            </div>
        </div>`;

        if (handlerEnterPaquete) document.removeEventListener('keypress', handlerEnterPaquete);
        handlerEnterPaquete = (e) => { if (e.key === 'Enter') { e.preventDefault(); avanzarPaquete(); } };
        document.addEventListener('keypress', handlerEnterPaquete);
        _agregarSwipeModal();
        return;
    }
    // ── Fin renderizado grupo serie ──
    modalEngaste.innerHTML = `
        <div style="background:white;border-radius:16px;overflow:hidden;box-shadow:0 8px 40px rgba(0,0,0,0.35);width:100%;max-width:975px;max-height:calc(100vh - 32px);display:flex;flex-direction:column;">

            <div style="background:#1e293b;color:white;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;gap:10px;flex-shrink:0;">
                <div style="display:flex;align-items:center;gap:12px;">
                    <div style="display:flex;flex-direction:column;align-items:center;">
                        <span style="font-size:0.7em;letter-spacing:1px;text-transform:uppercase;opacity:0.55;">Carro</span>
                        <div style="background:#f59e0b;color:#1e293b;padding:8px 22px;border-radius:8px;font-size:2.2em;font-weight:900;letter-spacing:1px;line-height:1;margin-top:2px;">🚗 ${carrosDelBono[carroActualIndex]?.carro ?? ''}</div>
                    </div>
                    <div style="font-size:0.95em;color:rgba(255,255,255,0.65);border-left:1px solid rgba(255,255,255,0.15);padding-left:14px;">${carrosDelBono[carroActualIndex]?.proyecto_nombre ?? ''}</div>
                </div>
                <div style="display:flex;align-items:center;gap:16px;">
                    <div style="text-align:right;">
                        <div style="font-size:0.7em;letter-spacing:1px;text-transform:uppercase;opacity:0.55;">Terminal</div>
                        <div style="font-size:1.25em;font-weight:700;margin-top:2px;">${terminalActual}</div>
                        <div style="font-size:0.8em;opacity:0.5;margin-top:1px;">${paqueteActualIndex + 1} / ${paquetesOrdenados.length}</div>
                    </div>
                    <button onclick="cancelarModalPaquetes()" title="Salir" style="background:rgba(255,255,255,0.12);border:1.5px solid rgba(255,255,255,0.25);color:white;border-radius:8px;width:40px;height:40px;font-size:1.2em;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;">&times;</button>
                </div>
            </div>

            <div id="engaste-scroll-body" style="flex:1;overflow-y:auto;padding:20px 24px 16px;">
            ${maquinaSeleccionada?.lleva_regulacion ? `
            <div onclick="verPdfRegulacionV3()" style="display:flex;align-items:center;gap:12px;background:#2d1b69;border:1.5px solid #a855f7;border-radius:10px;padding:11px 16px;margin-bottom:16px;cursor:${maquinaSeleccionada?.pdf_regulacion ? 'pointer' : 'default'};user-select:none;">
                <span style="font-size:1.5em;flex-shrink:0;">🔧</span>
                <div style="flex:1;">
                    <div style="font-size:0.82em;font-weight:700;color:#c4b5fd;letter-spacing:.04em;">ATENCI\u00d3N — M\u00c1QUINA CON REGULACI\u00d3N</div>
                    <div style="font-size:0.78em;color:rgba(196,181,253,.7);margin-top:2px;">${maquinaSeleccionada?.pdf_regulacion ? 'Toca para ver el PDF de regulaci\u00f3n' : 'Verifica que la regulaci\u00f3n es correcta antes de engastar'}</div>
                </div>
                ${maquinaSeleccionada?.pdf_regulacion ? '<span style="font-size:1.2em;opacity:.8;">\u2197\ufe0f</span>' : ''}
            </div>` : ''}
            <div style="text-align:center;margin-bottom:16px;">
                ${numeroEtiqueta ? `
                <div style="display:inline-flex;flex-direction:column;align-items:center;background:${_etq.bg};color:${_etq.text};padding:12px 34px;border-radius:12px;border:3px dashed rgba(0,0,0,0.25);box-shadow:0 4px 12px rgba(0,0,0,0.18);">
                    <span style="font-size:2.8em;font-weight:900;letter-spacing:2px;line-height:1;">${numeroEtiqueta}</span>
                    <span style="font-size:0.9em;font-weight:700;margin-top:4px;">${paquete.elemento}</span>
                </div>` : `<div style="font-size:1.5em;font-weight:700;color:#212529;">${paquete.elemento}</div>`}
            </div>

            <div style="display:grid;gap:12px;">
                
                ${cablesDeTerminal.length > 0 ? `
                    <div class="terminal-group terminal-group-azul" style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-left: 5px solid #2196f3; padding: 15px; border-radius: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                            <span style="font-size: 1.5em;">📍</span>
                            <span style="font-weight: bold; color: #0d2a4a; font-size: 1.15em;">De Terminal</span>
                            <span style="background: #bbdefb; color: #0d2a4a; padding: 4px 12px; border-radius: 12px; font-size: 1em; font-weight: bold; margin-left: auto; border: 1.5px solid #64b5f6;">
                                ${cablesDeTerminal.length}
                            </span>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            ${cablesDeTerminal.map(cable => 
                                `<span class="cable-badge" style="background: #bbdefb; color: #0d2a4a; padding: 9px 16px; border-radius: 8px; font-weight: 900; font-size: 1.1em; border: 1.5px solid #64b5f6;">${cable}</span>`
                            ).join('')}
                        </div>
                        <div style="margin-top: 10px; padding: 7px 12px; background: rgba(33,150,243,0.12); border-radius: 7px; display: flex; align-items: center; gap: 7px;">
                            <span style="font-size: 1.1em;">✅</span>
                            <span style="font-size: 0.88em; color: #1565c0; font-style: italic;">Pon el terminal en el lado <strong>liso</strong> del cable (el lado sin guion)</span>
                        </div>
                    </div>
                ` : ''}
                
                ${cablesParaTerminal.length > 0 ? `
                    <div class="terminal-group terminal-group-verde" style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-left: 5px solid #4caf50; padding: 15px; border-radius: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                            <span style="font-size: 1.5em;">🎯</span>
                            <span style="font-weight: bold; color: #1b5e20; font-size: 1.15em;">Para Terminal</span>
                            <span style="background: #c8e6c9; color: #1b5e20; padding: 4px 12px; border-radius: 12px; font-size: 1em; font-weight: bold; margin-left: auto; border: 1.5px solid #81c784;">
                                ${cablesParaTerminal.length}
                            </span>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            ${cablesParaTerminal.map(cable => 
                                `<span class="cable-badge" style="background: #c8e6c9; color: #1b5e20; padding: 9px 16px; border-radius: 8px; font-weight: 900; font-size: 1.1em; border: 1.5px solid #81c784;">${cable}</span>`
                            ).join('')}
                        </div>
                        <div style="margin-top: 10px; padding: 7px 12px; background: rgba(76,175,80,0.15); border-radius: 7px; display: flex; align-items: center; gap: 7px;">
                            <span style="font-size: 1.1em;">✂️</span>
                            <span style="font-size: 0.88em; color: #2e7d32; font-style: italic;">Pon el terminal en el lado del <strong>guion</strong> — la máquina de corte marca así todos los cables, ej: <strong>208-</strong></span>
                        </div>
                    </div>
                ` : ''}
                
                ${cablesAmbos.length > 0 ? `
                    <div class="terminal-group terminal-group-rojo" style="background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%); border-left: 5px solid #f44336; padding: 15px; border-radius: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                            <span style="font-size: 1.5em;">🔗</span>
                            <span style="font-weight: bold; color: #7f0000; font-size: 1.15em;">Ambos Lados</span>
                            <span style="background: #ffcdd2; color: #7f0000; padding: 4px 12px; border-radius: 12px; font-size: 1em; font-weight: bold; margin-left: auto; border: 1.5px solid #e57373;">
                                ${cablesAmbos.length}
                            </span>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            ${cablesAmbos.map(cable => 
                                `<span class="cable-badge" style="background: #ffcdd2; color: #7f0000; padding: 9px 16px; border-radius: 8px; font-weight: 900; font-size: 1.1em; border: 1.5px solid #e57373;">${cable}</span>`
                            ).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>

            <div style="padding-top:20px;padding-bottom:6px;text-align:right;">
                ${paquetesSaltados.length > 0 ? `<div style="font-size:0.78em;color:#e67e22;margin-bottom:6px;">⚠️ ${paquetesSaltados.length} saltado${paquetesSaltados.length>1?'s':''}</div>` : ''}
                <button onclick="avanzarPaquete()" style="padding:14px 32px;font-size:1.05em;font-weight:700;background:#0d6efd;color:white;border:none;border-radius:10px;cursor:pointer;min-width:180px;touch-action:manipulation;">
                    ${paqueteActualIndex === paquetesOrdenados.length - 1 ? '✅ Finalizar carro' : paqueteActualIndex === batchFinIndex - 1 ? '⏭️ Siguiente grupo' : 'Siguiente ▶'}
                </button>
            </div>

            </div>

            <div id="footer-paquete" style="padding:12px 20px;border-top:1px solid #e9ecef;background:#f8f9fa;flex-shrink:0;">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;">
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        ${paqueteActualIndex > 0 ? `<button onclick="volverPaqueteAnterior()" style="padding:8px 16px;font-size:0.88em;background:white;color:#495057;border:1.5px solid #ced4da;border-radius:8px;cursor:pointer;font-weight:600;">◀ Anterior</button>` : ''}
                        <button onclick="saltarPaquete()" style="padding:8px 16px;font-size:0.88em;background:#fff3cd;color:#856404;border:1.5px solid #ffc107;border-radius:8px;cursor:pointer;font-weight:600;">⤵️ Saltar</button>
                    </div>
                    <button onclick="document.getElementById('engaste-scroll-body')?.scrollTo({top:99999,behavior:'smooth'})" style="padding:10px 22px;font-size:1em;font-weight:700;background:#1e293b;color:white;border:none;border-radius:8px;cursor:pointer;touch-action:manipulation;">↓ Bajar</button>
                </div>
            </div>
        </div>
    `;

    // Remover handler anterior si existe
    if (handlerEnterPaquete) {
        document.removeEventListener('keypress', handlerEnterPaquete);
    }
    window._confirmandoFinal = false;
    
    // Enter y swipe para pasar al siguiente paquete
    handlerEnterPaquete = (e) => { if (e.key === 'Enter') { e.preventDefault(); avanzarPaquete(); } };
    document.addEventListener('keypress', handlerEnterPaquete);
    _agregarSwipeModal();
}

/**
 * Paquete completado - continuar con siguiente carro o finalizar
 */
async function paqueteCompletado() {
    try {
        const carroActual = carrosDelBono[carroActualIndex];
        const numSaltados = paquetesSaltados.length;

        if (numSaltados > 0) {
            // Hay saltados: guardar como pendientes, el carro NO se marca completado
            await fetch(`/api/bonos/${bonoActual.nombre}/progreso/parcial`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    terminal: terminalActual,
                    carro: carroActual.carro,
                    operario: operarioActual || '',
                    paquetes_hechos: paqueteActualIndex,
                    paquetes_pendientes: paquetesSaltados.map(p => ({
                        elemento: p.elemento,
                        cod_cable: p.cod_cable,
                        num_cables: p.num_cables,
                        bloqueado: !!p.bloqueado
                    }))
                })
            });
            const lista = paquetesSaltados.map(p => `• ${p.elemento} (${p.num_cables} cables)`).join('\n');
            mostrarMensaje(`⚠️ Carro ${carroActual.carro}: ${numSaltados} paquete${numSaltados>1?'s':''} pendiente${numSaltados>1?'s':''}. Deberás volver a este carro para completarlos:\n${lista}`, 'warning');
        } else {
            // Sin saltados: marcar carro como completado
            await fetch(`/api/bonos/${bonoActual.nombre}/progreso`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    terminal: terminalActual,
                    carro: carroActual.carro,
                    operario: operarioActual || '',
                    terminales_proyecto: [terminalActual]
                })
            });
            mostrarMensaje(`✅ Carro ${carroActual.carro} completado.`, 'success');
        }

        console.log(`${numSaltados > 0 ? '⚠️' : '✅'} Carro ${carroActual.carro} guardado (saltados: ${numSaltados})`);

    } catch (error) {
        console.error('Error al guardar progreso del carro:', error);
    }

    // Carro terminado (completo o parcial): limpiar su pantalla ESP32
    pushToESP32({ clear: true, carro: carrosDelBono[carroActualIndex]?.carro || '' });

    setTimeout(() => {
        document.getElementById('area-trabajo')?.classList.remove('fullscreen-engaste');
        const _me2 = document.getElementById('modal-engaste');
        if (_me2) _me2.remove();
        mostrarSeleccionCarro();
    }, paquetesSaltados.length > 0 ? 3500 : 1200);
}

/**
 * Terminar trabajo del terminal actual
 */
async function terminarTerminal() {
    // Liberar la sesión de trabajo activa (bloqueo concurrente)
    if (sesionActualId) {
        try {
            await fetch('/api/sesion/liberar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sesion_id: sesionActualId })
            });
        } catch(e) { /* ignorar si la red falla */ }
        sesionActualId = null;
    }
    // El progreso ya se guardó en paqueteCompletado() para cada carro procesado
    console.log(`✅ Terminal ${terminalActual} completado en todos sus carros`);
    
    // Marcar el terminal como 'completado' en el backend
    try {
        await fetch(`/api/bonos/${bonoActual.nombre}/progreso/estado`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ terminal: terminalActual, estado: 'completado', operario: operarioActual || '' })
        });
    } catch (e) { /* ignorar si falla */ }
    
    // Recargar progreso desde el backend para obtener estado actualizado
    await cargarProgresoDelBono(bonoActual.nombre);
    await cargarProgresoMaquina(); // Actualizar terminalesCompletados[] basado en progreso real
    
    // Forzar un repaint del DOM antes de continuar
    await new Promise(resolve => setTimeout(resolve, 100));

    // Verificar si terminamos todos los terminales de esta máquina
    if (terminalesCompletados.length === terminalesAsignados.length) {
        mostrarMensaje('🎉 ¡Todos los terminales completados!', 'success');
        setTimeout(() => {
            mostrarResumenFinal();
        }, 1000);
    } else {
        const pendientes = terminalesAsignados.length - terminalesCompletados.length;
        mostrarMensaje(`✅ Terminal completado. Quedan ${pendientes} pendiente${pendientes > 1 ? 's' : ''}.`, 'success');
        setTimeout(() => {
            abrirModalTerminal();
        }, 1200);
    }
    
    terminalActual = null;
    carroActualIndex = 0;
}

/**
 * Mostrar resumen final
 */
async function mostrarResumenFinal() {
    // Recargar el progreso completo del bono para tener datos actualizados
    await cargarProgresoDelBono(bonoActual.nombre);
    
    // Obtener terminales con datos del bono
    let terminalesConDatos = [];
    try {
        const response = await fetch(`/api/bonos/${encodeURIComponent(bonoActual.nombre)}/terminales-disponibles`);
        const data = await response.json();
        if (data.success) {
            terminalesConDatos = data.terminales || [];
        }
    } catch (error) {
        console.error('Error al obtener terminales disponibles:', error);
    }
    
    // Contar terminales completados en TODO el bono (no solo esta máquina)
    let totalTerminalesCompletadosBono = 0;
    if (window.progresoCompleto && terminalesConDatos.length > 0) {
        totalTerminalesCompletadosBono = terminalesConDatos.filter(terminal => {
            return window.progresoCompleto[terminal] && window.progresoCompleto[terminal].estado === 'completado';
        }).length;
    }
    
    console.log(`📊 Progreso total del bono: ${totalTerminalesCompletadosBono}/${terminalesConDatos.length}`);
    
    // Verificar si TODO el bono está completo
    if (totalTerminalesCompletadosBono >= terminalesConDatos.length && terminalesConDatos.length > 0) {
        // ¡BONO COMPLETADO!
        mostrarResumenBonoCompleto(terminalesConDatos.length);
        return;
    }
    
    // Verificar si quedan máquinas pendientes en este puesto
    let terminalesPendientesEnPuesto = 0;
    if (puestoSeleccionado && puestoSeleccionado.maquinas) {
        puestoSeleccionado.maquinas.filter(m => m.activo).forEach(maquina => {
            const todosTerminalesAsignados = maquina.terminales_asignados || [];
            const terminalesAsignados = terminalesConDatos.length > 0 
                ? todosTerminalesAsignados.filter(t => terminalesConDatos.includes(t))
                : todosTerminalesAsignados;
            
            terminalesAsignados.forEach(terminal => {
                const estaCompletado = window.progresoCompleto && 
                                      window.progresoCompleto[terminal] && 
                                      window.progresoCompleto[terminal].estado === 'completado';
                if (!estaCompletado) {
                    terminalesPendientesEnPuesto++;
                }
            });
        });
    }
    
    // Decidir el siguiente paso
    const siguientePaso = terminalesPendientesEnPuesto > 0 ? 'maquina' : 'puesto';
    const icono = terminalesPendientesEnPuesto > 0 ? '🔧' : '🏭';
    const mensajeSig = terminalesPendientesEnPuesto > 0
        ? `Quedan ${terminalesPendientesEnPuesto} terminal${terminalesPendientesEnPuesto > 1 ? 'es' : ''} en otras máquinas`
        : `Seleccionando otro puesto...`;

    // Celebración breve en el área de trabajo
    const areaTrabajoV2 = document.getElementById('area-trabajo');
    areaTrabajoV2.innerHTML = `
        <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:40px;border-radius:15px;text-align:center;">
            <div style="font-size:4em;margin-bottom:16px;">${icono}</div>
            <h2 style="font-size:2em;margin-bottom:12px;">¡Máquina completada!</h2>
            <div style="background:rgba(255,255,255,0.2);padding:18px;border-radius:10px;margin-bottom:18px;">
                <div style="font-size:2.8em;font-weight:bold;">${terminalesCompletados.length}</div>
                <div style="font-size:1.1em;">terminales procesados</div>
            </div>
            <p style="font-size:1em;opacity:0.85;">${mensajeSig}</p>
        </div>`;

    // Abrir el modal apropiado automáticamente
    await new Promise(resolve => setTimeout(resolve, 2200));
    await continuarDespuesDeCompletarMaquina(siguientePaso);
}

/**
 * Continuar después de completar una máquina
 */
async function continuarDespuesDeCompletarMaquina(siguientePaso) {
    if (siguientePaso === 'maquina') {
        await cargarProgresoDelBono(bonoActual.nombre);
        maquinaSeleccionada = null;
        terminalesAsignados = [];
        await abrirModalMaquina();
    } else if (siguientePaso === 'puesto') {
        await cargarProgresoDelBono(bonoActual.nombre);
        document.getElementById('paso-trabajo').classList.add('hidden');
        document.getElementById('workspace-v3').classList.add('hidden');
        puestoSeleccionado = null;
        await abrirModalPuesto();
    } else {
        window.location.href = '/';
    }
}

/**
 * Mostrar resumen cuando el BONO COMPLETO está terminado
 */
function mostrarResumenBonoCompleto(totalTerminales) {
    const areaTrabajoV2 = document.getElementById('area-trabajo');
    areaTrabajoV2.innerHTML = `
        <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 50px; border-radius: 15px; text-align: center;">
            <div style="font-size: 5em; margin-bottom: 20px;">🎊🎉🎊</div>
            <h2 style="font-size: 3em; margin-bottom: 20px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">¡BONO COMPLETADO!</h2>
            <p style="font-size: 1.5em; margin-bottom: 30px;">
                Has terminado <strong>TODOS</strong> los trabajos del bono <strong>${bonoActual.nombre}</strong>
            </p>
            <div style="background: rgba(255,255,255,0.25); padding: 30px; border-radius: 15px; margin-bottom: 30px;">
                <div style="font-size: 4em; font-weight: bold; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">${totalTerminales}</div>
                <div style="font-size: 1.3em;">Terminales procesados en total</div>
            </div>
            <p style="font-size: 1.2em; margin-bottom: 30px; font-style: italic;">
                ¡Excelente trabajo! 🏆
            </p>
            <button onclick="window.location.href='/'" class="btn-primary" style="padding: 20px 50px; font-size: 1.3em; background: white; color: #28a745; border: none; border-radius: 10px; cursor: pointer; font-weight: bold; box-shadow: 0 4px 6px rgba(0,0,0,0.2);">
                🏠 Volver al Inicio
            </button>
        </div>
    `;
}