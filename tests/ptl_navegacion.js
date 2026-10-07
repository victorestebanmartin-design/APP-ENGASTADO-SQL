async function probarNavegacionPtl() {
    const resultados = [];
    const fetchOriginal = window.fetch;
    const intervalOriginal = window.setInterval;
    const clearOriginal = window.clearInterval;
    const llamadas = [];
    const temporizadores = new Map();
    let estado = {};
    let cierre = {};
    let contador = 0;
    const comprobar = (condicion, mensaje) => {
        if (!condicion) throw new Error(mensaje);
    };
    const avanzar = async () => {
        for (const callback of [...temporizadores.values()]) await callback();
        for (let vuelta = 0; vuelta < 12; vuelta++) await Promise.resolve();
    };
    const preparar = () => {
        llamadas.length = 0;
        temporizadores.clear();
        document.body.innerHTML = '';
        puestoSeleccionado = { id: 'puesto_test' };
        gavetaLuzActual = { activo: true, led: 7, tipo: 'terminal', gaveta: 'Terminal A' };
        herramientaEnUso = { codigo: 'Tenaza', puesto_id: 'puesto_test' };
        estado = { success: true, led: 7, recogida: true, devuelta: false,
                   herramienta: { modo: 'en_uso' } };
        cierre = { success: true, gaveta: true, herramienta: true };
    };
    window.fetch = async (url) => {
        llamadas.push(url);
        return { json: async () => url.endsWith('/cierre') ? cierre : { ...estado } };
    };
    window.setInterval = callback => {
        const identificador = ++contador;
        temporizadores.set(identificador, callback);
        return identificador;
    };
    window.clearInterval = identificador => temporizadores.delete(identificador);
    try {
        preparar();
        let terminado = false;
        const cambio = devolverGavetaAlCambiarTerminal().then(() => { terminado = true; });
        await avanzar();
        comprobar(document.getElementById('gaveta-devolucion-overlay'), 'Falta el panel al cambiar terminal');
        comprobar(!terminado, 'El cambio no espera la devolucion');
        comprobar(!llamadas.some(url => url.endsWith('/apagar')), 'Apaga antes de devolver');
        estado.devuelta = true;
        await avanzar();
        await cambio;
        comprobar(herramientaEnUso?.codigo === 'Tenaza', 'No conserva la tenaza');
        comprobar(llamadas.some(url => url.endsWith('/apagar')), 'No apaga tras devolver');
        comprobar(!llamadas.some(url => url.includes('/progreso')), 'Modifica el progreso pendiente');
        resultados.push('Cambiar terminal espera gaveta, conserva tenaza y progreso');

        preparar();
        estado.recogida = false;
        await devolverGavetaAlCambiarTerminal();
        comprobar(!document.getElementById('gaveta-devolucion-overlay'), 'Pide devolver una gaveta no sacada');
        comprobar(llamadas.some(url => url.endsWith('/apagar')), 'No apaga una gaveta no sacada');
        resultados.push('Gaveta iluminada sin sacar: se apaga sin esperar');

        preparar();
        let omitido = false;
        const omision = devolverGavetaAlCambiarTerminal().then(() => { omitido = true; });
        await avanzar();
        const boton = document.getElementById('gaveta-continuar');
        boton.click();
        await avanzar();
        comprobar(!omitido, 'Un solo clic omite la devolucion');
        boton.click();
        await omision;
        comprobar(!llamadas.some(url => url.endsWith('/apagar')), 'La omision borra el aviso');
        resultados.push('Omision exige dos clics y no apaga el aviso');

        preparar();
        const salida = cerrarPtlAlSalir();
        await avanzar();
        comprobar(document.getElementById('gaveta-devolucion-overlay'), 'Salir no pide la gaveta');
        estado.led = null;
        await avanzar();
        comprobar(document.getElementById('herramienta-devolucion-overlay'), 'Salir no pide la tenaza');
        estado.herramienta = null;
        await avanzar();
        await salida;
        comprobar(!gavetaLuzActual && !herramientaEnUso, 'No limpia el estado local al salir');
        comprobar(!llamadas.some(url => url.endsWith('/apagar')), 'Salir borra los avisos del servidor');
        resultados.push('Salir espera gaveta y tenaza y reconoce la orden cerrada');

        preparar();
        const salidaOmitida = cerrarPtlAlSalir();
        await avanzar();
        document.getElementById('gaveta-continuar').click();
        document.getElementById('gaveta-continuar').click();
        await avanzar();
        document.getElementById('herramienta-continuar').click();
        comprobar(document.getElementById('herramienta-devolucion-overlay'), 'Una pulsacion omite la tenaza');
        document.getElementById('herramienta-continuar').click();
        await salidaOmitida;
        comprobar(!llamadas.some(url => url.endsWith('/apagar')), 'Omitir al salir apaga las alarmas');
        resultados.push('Omitir ambas devoluciones conserva las alarmas');

        preparar();
        gavetaLuzActual = null;
        herramientaEnUso = null;
        await cerrarPtlAlSalir();
        await devolverGavetaAlCambiarTerminal();
        comprobar(llamadas.length === 0, 'Sin PTL no deberia llamar al servidor');
        resultados.push('Sin PTL no se bloquea ni hace peticiones');

        preparar();
        document.body.innerHTML = '<div id="modal-terminal-subtitulo"></div><div id="modal-terminal-contenido"></div>';
        bonoActual = { nombre: 'bono_test' };
        maquinaSeleccionada = { nombre: 'maquina_test', terminales_asignados: [] };
        terminalesCompletados = [];
        let listaAbierta = false;
        window._mostrarModalWizard = () => { listaAbierta = true; };
        window.avisarAtencionGaveta = () => {};
        window.cargarProgresoMaquina = async () => {};
        const abrirLista = abrirModalTerminal();
        await avanzar();
        comprobar(!listaAbierta, 'El boton abre la lista antes de devolver');
        estado.devuelta = true;
        await avanzar();
        await abrirLista;
        comprobar(listaAbierta, 'No abre la lista despues de devolver');
        comprobar(herramientaEnUso?.codigo === 'Tenaza', 'El boton devuelve tambien la tenaza');
        resultados.push('El boton real Cambiar terminal espera antes de abrir la lista');

        preparar();
        puestoBloqueadoPorRfid = true;
        window.mostrarMensaje = () => {};
        window.abrirModalMaquina = async () => {};
        await volverAPuestos();
        comprobar(llamadas.length === 0, 'Un cambio de puesto rechazado pide devolver');
        comprobar(herramientaEnUso && gavetaLuzActual, 'Un cambio rechazado limpia el PTL');
        resultados.push('Puesto fijado por RFID: cambio rechazado conserva el PTL');
        return resultados;
    } finally {
        detenerVigilanciaGaveta();
        window.fetch = fetchOriginal;
        window.setInterval = intervalOriginal;
        window.clearInterval = clearOriginal;
    }
}