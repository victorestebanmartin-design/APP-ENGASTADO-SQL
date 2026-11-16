"""
Genera el hash (con sal) de un PIN de administración.

Ya no hace falta para el uso normal: si el PC no tiene PIN fijado, la app lo
pide sola la primera vez que se entra en /admin. Este script sigue sirviendo
para fijarlo de antemano (despliegues automatizados) o para forzar uno fijo
que ignore lo que se configure luego desde Admin -> Sistema.

Uso:
    python _scripts_utiles/generar_pin_hash.py

Pide el PIN por consola (sin eco) y muestra la línea lista para pegar
en el fichero .env del proyecto:

    ADMIN_PIN_HASH=<hash>

El PIN en claro NUNCA se guarda ni se muestra; solo su hash.
"""
import getpass

from werkzeug.security import generate_password_hash


def main():
    print("Generador de hash de PIN para el módulo de administración")
    print("=" * 56)
    pin = getpass.getpass("Introduce el PIN: ").strip()
    if not pin:
        print("ERROR: el PIN no puede estar vacío.")
        return
    pin2 = getpass.getpass("Repite el PIN: ").strip()
    if pin != pin2:
        print("ERROR: los PIN no coinciden.")
        return

    # Con sal, igual que app/auth.py:hash_pin. Los SHA-256 que generaba antes
    # este script siguen valiendo en el .env; este formato aguanta mejor.
    hash_pin = generate_password_hash(pin)

    print()
    print("Añade (o reemplaza) esta línea en tu fichero .env:")
    print()
    print(f"ADMIN_PIN_HASH={hash_pin}")
    print()
    print("Reinicia la app para que la protección quede activa.")


if __name__ == "__main__":
    main()
