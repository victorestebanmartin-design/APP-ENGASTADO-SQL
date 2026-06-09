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
import ssl
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

def pa_request(method, url, token, data=None):
    headers = {"Authorization": f"Token {token}"}
    body = None
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = urlencode(data).encode("utf-8")
    req = Request(url, data=body, headers=headers, method=method)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(req, timeout=60, context=ctx) as resp:
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

def pa_upload_file(username, token, remote_path, local_path):
    """Sube un archivo directamente a PA via API (multipart/form-data)."""
    url = f"https://www.pythonanywhere.com/api/v0/user/{username}/files/path{remote_path}"
    with open(local_path, 'rb') as f:
        content = f.read()
    boundary = "----PAboundary1234567890"
    filename = os.path.basename(local_path)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="content"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    req = Request(url, data=body, headers=headers, method="POST")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(req, timeout=60, context=ctx) as resp:
            return resp.status
    except HTTPError as e:
        # 200 o 201 = ok, intenta leer body si es 4xx
        try:
            print(f"    HTTP {e.code}: {e.read().decode('utf-8','replace')[:120]}")
        except Exception:
            pass
        return e.code

def pa_git_pull(domain, deploy_secret, username, token):
    print("\n[2/3] Sync en PythonAnywhere...")
    url = f"https://{domain}/api/internal/deploy-pull"
    headers = {"X-Deploy-Token": deploy_secret, "Content-Type": "application/x-www-form-urlencoded"}
    req = Request(url, data=b"", headers=headers, method="POST")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(req, timeout=30, context=ctx) as resp:
            raw = resp.read().decode("utf-8").strip()
            data = json.loads(raw) if raw else {}
            if data.get("success"):
                out = data.get("stdout", "").strip()
                if out:
                    print(f"  {out}")
                print("  OK")
                return
            else:
                print(f"  Hook respondio pero fallo: {data}")
    except Exception as e:
        print(f"  Hook no disponible ({e}), usando upload directo...")

    # El home en PA es /home/Viktor85 (capital V aunque el username es viktor85)
    pa_home = os.environ.get("PA_HOME", f"/home/Viktor85")
    project = f"{pa_home}/APP-ENGASTADO-SQL"
    files_to_sync = [
        ("app/routes.py",           f"{project}/app/routes.py"),
        ("app/__init__.py",         f"{project}/app/__init__.py"),
        ("repositories/__init__.py",f"{project}/repositories/__init__.py"),
        ("deploy.py",               f"{project}/deploy.py"),
        ("schema_sqlite.sql",       f"{project}/schema_sqlite.sql"),
        ("templates/admin.html",           f"{project}/templates/admin.html"),
        ("static/css/style-admin.css",     f"{project}/static/css/style-admin.css"),
        ("static/js/admin.js",             f"{project}/static/js/admin.js"),
    ]
    base = os.path.dirname(__file__)
    ok = 0
    for local_rel, remote in files_to_sync:
        local = os.path.join(base, local_rel.replace("/", os.sep))
        if not os.path.exists(local):
            continue
        status = pa_upload_file(username, token, remote, local)
        if status in (200, 201):
            ok += 1
        else:
            print(f"  AVISO upload {local_rel}: {status}")
    print(f"  Upload directo: {ok}/{len(files_to_sync)} archivos OK")

def pa_reload(username, domain, token):
    print(f"\n[3/3] Recargando app ({domain})...")
    try:
        status, data = pa_request(
            "POST",
            f"https://www.pythonanywhere.com/api/v0/user/{username}/webapps/{domain}/reload/",
            token
        )
        if status == 200:
            print("  App recargada correctamente.")
        else:
            print(f"  AVISO al recargar: {status} {data}")
    except Exception as e:
        print(f"  AVISO: timeout/error en reload ({e})")
        print("  Es posible que la app se haya recargado igualmente. Comprueba manualmente.")

def pa_backup_db(username, token):
    """Descarga la BD de PythonAnywhere y la guarda como backup con timestamp."""
    import datetime
    pa_home = os.environ.get("PA_HOME", f"/home/Viktor85")
    remote_db = f"{pa_home}/APP-ENGASTADO-SQL/data/engastado.db"
    url = f"https://www.pythonanywhere.com/api/v0/user/{username}/files/path{remote_db}"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = Request(url, headers={"Authorization": f"Token {token}"})
    try:
        with urlopen(req, context=ctx, timeout=60) as resp:
            content = resp.read()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(os.path.dirname(__file__), "data", f"engastado.db.backup_PA_{ts}")
        with open(backup_path, "wb") as f:
            f.write(content)
        print(f"  Backup guardado: data/engastado.db.backup_PA_{ts} ({len(content)//1024} KB)")
        return backup_path
    except Exception as e:
        print(f"  AVISO: no se pudo descargar backup ({e})")
        return None


def main():
    load_env()
    username = os.environ["PA_USERNAME"]
    domain   = os.environ["PA_DOMAIN"]
    token    = os.environ["PA_TOKEN"]

    deploy_secret = os.environ["DEPLOY_SECRET"]
    args = sys.argv[1:]

    # Modo backup: python deploy.py --backup
    if args and args[0] == "--backup":
        print("\nDescargando backup de BD de PythonAnywhere...")
        pa_backup_db(username, token)
        return

    commit_message = " ".join(args) if args else "deploy"

    print(f"\nDesplegando '{commit_message}' -> {domain}")
    print("=" * 50)

    git_push(commit_message)
    pa_git_pull(domain, deploy_secret, username, token)
    pa_reload(username, domain, token)

    # Backup automático post-deploy
    print("\n[4/4] Backup BD de PythonAnywhere...")
    pa_backup_db(username, token)

    print("\n" + "=" * 50)
    print(f"Deploy completado: https://{domain}")

if __name__ == "__main__":
    main()
