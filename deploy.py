#!/usr/bin/env python3
"""
Deploy script: git push + PythonAnywhere pull & reload en un solo comando.

Uso:
    python deploy.py "mensaje del commit"
    python deploy.py          <- usa mensaje "deploy"
"""

import os
import sys
import subprocess
import json
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

# --- Cargar .env manualmente (sin dependencias extra) ---
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        print("ERROR: No se encuentra el archivo .env")
        sys.exit(1)
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

def run(cmd, check=True):
    print(f"  > {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if check and result.returncode != 0:
        print(f"\nERROR: el comando falló (código {result.returncode})")
        sys.exit(result.returncode)
    return result

def pa_request(method, url, token, data=None):
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = urlencode(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except HTTPError as e:
        return e.code, e.read().decode()

def git_push(commit_message):
    print("\n[1/3] Git push a GitHub...")
    status = run("git status --porcelain", check=False)
    if status.stdout.strip():
        run("git add .")
        run(f'git commit -m "{commit_message}"')
    else:
        print("  (nada que commitear, haciendo push de lo pendiente)")
    run("git push")
    print("  OK")

def pa_git_pull(username, project_path, token):
    print("\n[2/3] Git pull en PythonAnywhere...")
    base = f"https://www.pythonanywhere.com/api/v0/user/{username}"

    # Crear una consola bash
    status, data = pa_request("POST", f"{base}/consoles/", token,
                               {"executable": "bash", "arguments": "",
                                "working_directory": f"/home/{username}"})
    if status not in (200, 201):
        print(f"  ERROR creando consola: {status} {data}")
        sys.exit(1)

    console_id = data["id"]

    # Ejecutar git pull (path entre comillas por si tiene espacios o acentos)
    cmd = f"git -C '{project_path}' pull origin main\n"
    status2, _ = pa_request("POST", f"{base}/consoles/{console_id}/send_input/",
                              token, {"input": cmd})
    if status2 != 200:
        print(f"  AVISO: no se pudo enviar git pull ({status2})")
    else:
        time.sleep(4)
        status3, out = pa_request("GET", f"{base}/consoles/{console_id}/get_latest_output/", token)
        if status3 == 200 and isinstance(out, dict):
            print(out.get("output", "").strip())

    print("  OK")

def pa_reload(username, domain, token):
    print(f"\n[3/3] Recargando app ({domain})...")
    status, data = pa_request(
        "POST",
        f"https://www.pythonanywhere.com/api/v0/user/{username}/webapps/{domain}/reload/",
        token
    )
    if status == 200:
        print("  App recargada correctamente.")
    else:
        print(f"  ERROR al recargar: {status} {data}")
        sys.exit(1)

def main():
    load_env()
    username     = os.environ["PA_USERNAME"]
    domain       = os.environ["PA_DOMAIN"]
    token        = os.environ["PA_TOKEN"]
    project_path = os.environ.get("PA_PROJECT_PATH", "")

    if not project_path:
        print("ERROR: Falta PA_PROJECT_PATH en el archivo .env")
        print("       Ejemplo: PA_PROJECT_PATH=/home/viktor85/APP-ENGASTADO-SQL")
        sys.exit(1)

    commit_message = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "deploy"

    print(f"\nDesplegando '{commit_message}' -> {domain}")
    print("=" * 50)

    git_push(commit_message)
    pa_git_pull(username, project_path, token)
    pa_reload(username, domain, token)

    print("\n" + "=" * 50)
    print(f"Deploy completado: https://{domain}")

if __name__ == "__main__":
    main()
