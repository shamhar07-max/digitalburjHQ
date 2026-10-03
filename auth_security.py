"""Owner authenticator verification (RFC 6238 TOTP)."""
import base64,hashlib,hmac,os,struct,time

def verify_totp(code,at=None):
 secret=os.environ.get('HQ_OWNER_TOTP_SECRET')
 if not secret:return os.environ.get('HQ_ENV')!='production'
 if not isinstance(code,str) or len(code)!=6 or not code.isdigit():return False
 try:key=base64.b32decode(secret.upper()+'='*((8-len(secret)%8)%8))
 except Exception:return False
 counter=int((at if at is not None else time.time())//30)
 for step in [counter-1,counter,counter+1]:
  digest=hmac.new(key,struct.pack('>Q',step),hashlib.sha1).digest();offset=digest[-1]&15
  value=(struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000
  if hmac.compare_digest(code,f'{value:06}'):return True
 return False
