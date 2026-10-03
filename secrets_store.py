"""Encrypted external-service token storage shared by application workers."""
import json,os
from cryptography.fernet import Fernet

def cipher():
 key=os.environ.get('HQ_TOKEN_ENCRYPTION_KEY')
 if not key:raise ValueError('Configure HQ_TOKEN_ENCRYPTION_KEY before connecting external services.')
 return Fernet(key.encode())
def put(c,key,value):
 encrypted=cipher().encrypt(json.dumps(value).encode()).decode()
 c.execute('INSERT INTO service_tokens VALUES(?,?) ON CONFLICT(name) DO UPDATE SET encrypted=excluded.encrypted',(key,encrypted))
def get(c,key):
 row=c.execute('SELECT encrypted FROM service_tokens WHERE name=?',(key,)).fetchone()
 return json.loads(cipher().decrypt(row['encrypted'].encode())) if row else None
def delete(c,key):c.execute('DELETE FROM service_tokens WHERE name=?',(key,))
