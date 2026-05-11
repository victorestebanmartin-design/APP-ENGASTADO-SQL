import sqlite3
conn = sqlite3.connect('data/engastado.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
for t in cur.fetchall():
    cur2 = conn.cursor()
    cur2.execute('SELECT COUNT(*) FROM ' + t[0])
    print(t[0], '->', cur2.fetchone()[0])
conn.close()
