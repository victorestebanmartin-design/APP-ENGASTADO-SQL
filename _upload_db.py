import ssl, os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

token = '1e6a702146a3721cef95aee458f3c546d5bf3955'
local = r'C:\Users\estebanv\APP-ENGASTADO-SQL\data\engastado.db.backup_20260218_163849'
remote = '/home/Viktor85/APP-ENGASTADO-SQL/data/engastado.db'
url = f'https://www.pythonanywhere.com/api/v0/user/viktor85/files/path{remote}'

with open(local, 'rb') as f:
    content = f.read()

boundary = '----PAboundary1234567890'
body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="content"; filename="engastado.db"\r\n'
    f'Content-Type: application/octet-stream\r\n\r\n'
).encode() + content + f'\r\n--{boundary}--\r\n'.encode()

headers = {
    'Authorization': f'Token {token}',
    'Content-Type': f'multipart/form-data; boundary={boundary}',
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
req = Request(url, data=body, headers=headers, method='POST')
try:
    with urlopen(req, timeout=120, context=ctx) as r:
        print(f'OK: {r.status} - DB subida ({len(content):,} bytes)')
except HTTPError as e:
    print(f'ERROR {e.code}: {e.read().decode("utf-8","replace")[:300]}')
except Exception as e:
    print(f'ERROR: {e}')
