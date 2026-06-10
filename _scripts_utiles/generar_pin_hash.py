"""
Genera el hash SHA-256 de un PIN de administración.

Uso:
    python _scripts_utiles/generar_pin_hash.py

Pide el PIN por consola (sin eco) y muestra la línea lista para pegar
en el fichero .env del proyecto:

    ADMIN_PIN_HASH=<hash>

El PIN en claro NUNCA se guarda ni se muestra; solo su hash.
"""
import hashlib
import getpass


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

    hash_pin = hashlib.sha256(pin.encode("utf-8")).hexdigest()

    print()
    print("Añade (o reemplaza) esta línea en tu fichero .env:")
    print()
    print(f"ADMIN_PIN_HASH={hash_pin}")
    print()
    print("Reinicia la app para que la protección quede activa.")


if __name__ == "__main__":
    main()
