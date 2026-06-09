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
from urllib.error import HTTPError, URLError

# --- Cargar .env manualmente (sin dependencias extra) ---
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        print("ERROR: No se encuentra el archivo .env")
        sys.exit(1)
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

GIT = r"C:\Users\estebanv\AppData\Local\GitHubDesktop\app-3.5.8\resources\app\git\cmd\git.exe"

def run(cmd, check=True):
    cmd = cmd.replace("git ", f'"{GIT}" ', 1) if cmd.startswith("git ") else cmd
    print(f"  > {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if check and result.returncode != 0:
        print(f"\nERROR: el comando fallo (codigo {result.returncode})")
        sys.exit(result.returncode)
    return result

def pa_request(method, url, token, data=None, deploy_hook=False):
    if deploy_hook:
        headers = {"X-Deploy-Token": token, "Content-Type": "application/x-www-form-urlencoded"}
    else:
        headers = {"Authorization": f"Token {token}"}
    body = None
    if data and not deploy_hook:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = urlencode(data).encode("utf-8")
    elif deploy_hook:
        body = b""  # POST sin cuerpo
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8").strip()
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"_raw": raw[:200]}
            return status, parsed
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace").strip()
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, {"_raw": raw[:200]}
    except URLError as e:
        return 0, {"error": str(e)}

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

def pa_git_pull(domain, token):
    print("\n[2/3] Git pull en PythonAnywhere...")
    url = f"https://{domain}/api/internal/deploy-pull"
    status, data = pa_request("POST", url, token, deploy_hook=True)
    if status == 200 and isinstance(data, dict) and data.get("success"):
        out = data.get("stdout", "").strip()
        if out:
            print(f"  {out}")
        print("  OK")
    elif status == 404:
        print("  AVISO: deploy hook no encontrado en la app (primera vez).")
        print("  Haz 'git pull' manualmente en PythonAnywhere esta vez.")
    else:
        print(f"  AVISO: respuesta inesperada ({status}): {data}")
        print("  Haz 'git pull' manualmente en PythonAnywhere.")

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
    username = os.environ["PA_USERNAME"]
    domain   = os.environ["PA_DOMAIN"]
    token    = os.environ["PA_TOKEN"]

    commit_message = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "deploy"

    print(f"\nDesplegando '{commit_message}' -> {domain}")
    print("=" * 50)

    git_push(commit_message)
    pa_git_pull(domain, token)
    pa_reload(username, domain, token)

    print("\n" + "=" * 50)
    print(f"Deploy completado: https://{domain}")

if __name__ == "__main__":
    main()
