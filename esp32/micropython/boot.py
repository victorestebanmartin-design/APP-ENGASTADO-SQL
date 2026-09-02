# WebREPL es opcional: sin webrepl_cfg.py, webrepl.start() lanza TypeError y,
# al fallar boot.py, MicroPython NO ejecuta main.py -> la pantalla se queda
# negra. Se envuelve para que un WebREPL sin configurar nunca impida arrancar.
try:
    import webrepl
    webrepl.start()
except Exception as _e:
    print("WebREPL no arrancado:", _e)
