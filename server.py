#!/usr/bin/env python3
"""DigitalBurj HQ — dependency-free internal workspace server."""
import argparse, datetime, hashlib, hmac, http.cookies, json, mimetypes, os, pathlib, secrets, sqlite3, time
STATIC_TYPES={'.webmanifest':'application/manifest+json','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8'}
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import hq_features as features
import integrations
import database
import account_mail
import auth_security
import hq_collab as collab
import r2
import logging
ROOT=pathlib.Path(__file__).parent
DB=pathlib.Path(os.environ.get('HQ_DB',str(ROOT/'hq.sqlite3')))
DEPTS=['Business OS','Academy','Studio','Growth']
ROLES=['admin','manager','teacher','developer','designer','growth']
COOKIE='db_hq_session'
OWNER_EMAIL='shamhar07@gmail.com'
BOOTSTRAP=pathlib.Path(os.environ.get('HQ_BOOTSTRAP',str(ROOT/'owner_account.json')))
def is_owner(user):
 return bool(user and user['email']==OWNER_EMAIL and user['role']=='admin')
def connection():
 return database.connection(DB)
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
def pw_hash(password):
 salt=secrets.token_hex(16);return salt+':'+hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def pw_ok(password,value):
 salt,digest=value.split(':');return hmac.compare_digest(digest,hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex())
def public(row,c=None):
 result={k:row[k] for k in ['id','name','email','role','department','active']};result['can_invite']=is_owner(row)
 if c is not None:result['permissions']=features.permissions(c,row)
 else:
  with connection() as current:result['permissions']=features.permissions(current,row)
 return result
def audit(c,user,action,target):c.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',(user,action,str(target),stamp()))
def init():
 with connection() as c:
  if c.is_postgres:
   database.verify(c)
  else:c.executescript('''
 CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,department TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
 CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),csrf TEXT NOT NULL,expires REAL NOT NULL);
 CREATE TABLE IF NOT EXISTS invitations(token TEXT PRIMARY KEY,email TEXT NOT NULL,role TEXT NOT NULL,department TEXT NOT NULL,expires REAL NOT NULL,used INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,department TEXT NOT NULL,owner TEXT REFERENCES users(id),status TEXT NOT NULL,priority TEXT NOT NULL,due TEXT NOT NULL,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,title TEXT NOT NULL,department TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL,feedback TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS announcements(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,department TEXT NOT NULL,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT,action TEXT,target TEXT,created TEXT);
 CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER,until REAL);
 ''')
 with connection() as c:
  if not c.is_postgres:features.init(c);integrations.init(c);account_mail.init(c);collab.init(c)
  else:integrations.register_permissions()
 if BOOTSTRAP.is_file():
  b=json.loads(BOOTSTRAP.read_text())
  if b.get('email')!=OWNER_EMAIL:raise RuntimeError('Invalid HQ owner configuration')
  with connection() as c:
   if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
    c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',(secrets.token_hex(12),b.get('name','Shameem'),OWNER_EMAIL,b['password_hash'],'admin','Business OS'))
    audit(c,None,'Owner account initialized','HQ owner')
class Handler(BaseHTTPRequestHandler):
 def log_message(self,fmt,*args):pass
 def send(self,status,data=None,headers=None):
  payload=json.dumps(data or {},ensure_ascii=False).encode();self.send_response(status)
  self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
  for k,v in (headers or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(payload)
 def user(self,c):
  cookie=http.cookies.SimpleCookie(self.headers.get('Cookie','')); token=cookie.get(COOKIE)
  if not token:return None,None
  session=c.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(token.value.encode()).hexdigest(),time.time())).fetchone()
  if not session:return None,None
  u=c.execute('SELECT * FROM users WHERE id=? AND active=1',(session['user_id'],)).fetchone();return u,session
 def do_GET(self):
  if self.path=='/healthz':return self.send(200,{'status':'ok'})
  if self.path=='/readyz':
   try:
    with connection() as c:
     c.execute('SELECT 1').fetchone();database.verify(c)
    return self.send(200,{'status':'ready'})
   except Exception:return self.send(503,{'status':'unavailable'})
  if self.path.split('?')[0].startswith('/api/'):
   with connection() as c:
    u,s=self.user(c)
    try:
     if integrations.get(self,c,u,s):return
    except ValueError as e:return self.send(400,{'error':str(e)})
    try:
     if collab.get(self,c,u):return
    except (ValueError,TypeError) as e:return self.send(400,{'error':str(e)})
    if not u:return self.send(401,{'error':'Sign in to continue.'})
    if self.path=='/api/me':return self.send(200,{'user':public(u,c),'csrf':s['csrf']})
    if self.path!='/api/workspace':return self.send(404,{'error':'Not found'})
    return self.send(200,features.workspace(c,u,lambda row:public(row,c)))
  path=self.path.split('?')[0];p=ROOT/'public'/('index.html' if path=='/' else path.lstrip('/'))
  try:p=p.resolve();p.relative_to((ROOT/'public').resolve())
  except ValueError:return self.send(403)
  if not p.is_file():return self.send(404)
  self.send_response(200);self.send_header('Content-Type',STATIC_TYPES.get(p.suffix) or mimetypes.guess_type(str(p))[0] or 'application/octet-stream');self.send_header('Cache-Control','no-cache' if p.suffix in ('.html','.js','.css','.webmanifest') else 'public, max-age=86400');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','same-origin');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://*.r2.cloudflarestorage.com; font-src 'self'; connect-src 'self'; frame-src 'self' https://*.r2.cloudflarestorage.com; manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'");self.end_headers();self.wfile.write(p.read_bytes())
 def upload(self):
  """Raw-body file upload. Storage I/O runs outside any database transaction or global write lock."""
  length=int(self.headers.get('Content-Length',0))
  if length>collab.MAX_UPLOAD:return self.send(413,{'error':'Files can be at most %d MB.'%(collab.MAX_UPLOAD//1048576)})
  if self.headers.get('Origin') and self.headers['Origin']!=('https://' if os.environ.get('HQ_SECURE_COOKIE')=='1' else 'http://')+self.headers.get('Host',''):return self.send(403,{'error':'Origin rejected'})
  with connection() as c:
   u,s=self.user(c)
   if not u:return self.send(401,{'error':'Sign in to continue.'})
   if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']):return self.send(403,{'error':'Session validation failed. Reload and try again.'})
   plan=collab.plan_upload(c,u,length,collab.query(self))
  data=self.rfile.read(length);collab.check_content(plan,data)
  store=r2.files_store();key='files/'+collab.uid();store.put(key,data,plan['mime'])
  try:
   with connection() as c:meta=collab.record_upload(c,u,plan,key,data)
  except Exception:
   try:store.delete(key)
   except r2.StorageError:pass
   raise
  return self.send(201,meta)
 def do_POST(self):
  try:
   if self.path.split('?')[0]=='/api/files/upload':return self.upload()
   if int(self.headers.get('Content-Length',0))>32768:return self.send(413)
   if self.headers.get('Origin') and self.headers['Origin']!=('https://' if os.environ.get('HQ_SECURE_COOKIE')=='1' else 'http://')+self.headers.get('Host',''):return self.send(403,{'error':'Origin rejected'})
   raw=self.rfile.read(int(self.headers.get('Content-Length',0)))
   b=json.loads(raw or '{}')
   if not isinstance(b,dict):raise ValueError('Invalid request')
   with connection() as c:
    if c.is_postgres:c.execute('SELECT pg_advisory_xact_lock(72844002)')
    if account_mail.post(self,c,b,pw_hash):return
    if self.path=='/api/stripe/webhook':return integrations.stripe_event(self,c,b,raw)
    if self.path=='/api/partner/checkout':return integrations.checkout(self,c,b)
    if integrations.post(self,c,b,raw,pw_hash,pw_ok):return
    if self.path=='/api/login':
     email=str(b.get('email','')).strip().lower()
     if len(str(b.get('password','')))>256 or len(email)>254:raise ValueError('Invalid sign-in details.')
     key=self.client_address[0]+':'+email;now=time.time();a=c.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
     if a and a['until']>now and a['count']>=8:return self.send(429,{'error':'Too many attempts. Try again in 15 minutes.'})
     u=c.execute('SELECT * FROM users WHERE email=? AND active=1',(email,)).fetchone()
     if not u or not pw_ok(str(b.get('password','')),u['password']) or (is_owner(u) and not auth_security.verify_totp(str(b.get('otp','')))):
      count=a['count']+1 if a and a['until']>now else 1;c.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(key,count,now+900));return self.send(401,{'error':'Email or password is incorrect.'})
     c.execute('DELETE FROM attempts WHERE key=?',(key,));token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],csrf,now+28800));audit(c,u['id'],'Signed in',u['id'])
     return self.send(200,{'user':public(u,c),'csrf':csrf},{'Set-Cookie':COOKIE+'='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800'+('; Secure' if os.environ.get('HQ_SECURE_COOKIE')=='1' else '')})
    if self.path=='/api/accept-invite':
     token=hashlib.sha256(str(b.get('token','')).encode()).hexdigest();i=c.execute('SELECT * FROM invitations WHERE token=? AND used=0 AND expires>?',(token,time.time())).fetchone()
     if not i:raise ValueError('Invitation is invalid or expired.')
     name=str(b.get('name','')).strip();password=str(b.get('password',''))
     if not name or len(name)>100 or not 12<=len(password)<=256:raise ValueError('Enter your name and a password of at least 12 characters.')
     uid=secrets.token_hex(12);c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',(uid,name,i['email'],pw_hash(password),i['role'],i['department']));c.execute('UPDATE invitations SET used=1 WHERE token=?',(token,));audit(c,uid,'Accepted invitation',i['department']);return self.send(201,{'ok':True})
    u,s=self.user(c)
    if not u:return self.send(401,{'error':'Sign in to continue.'})
    if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']):return self.send(403,{'error':'Session validation failed. Reload and try again.'})
    if integrations.owner_post(self,c,u,b):return
    if features.post(self,c,u,b):return
    if collab.post(self,c,u,b):return
    admin=is_owner(u);manager=admin;dept=str(b.get('department',u['department']))
    def scoped(value):return admin or value==u['department']
    if self.path=='/api/change-password':
     if not pw_ok(str(b.get('current','')),u['password']):raise ValueError('Current password is incorrect.')
     password=str(b.get('password',''))
     if len(password)<12:raise ValueError('New passwords must contain at least 12 characters.')
     c.execute('UPDATE users SET password=? WHERE id=?',(pw_hash(password),u['id']))
     c.execute('DELETE FROM sessions WHERE user_id=? AND token!=?',(u['id'],s['token']));audit(c,u['id'],'Changed password',u['id']);return self.send(200,{'ok':True})
    if self.path=='/api/revoke-invite':
     if not is_owner(u):return self.send(403,{'error':'Owner access required.'})
     c.execute('DELETE FROM invitations WHERE token=? AND used=0',(b.get('id'),));audit(c,u['id'],'Revoked invitation','Staff invitation');return self.send(200,{'ok':True})
    if self.path=='/api/logout':c.execute('DELETE FROM sessions WHERE token=?',(s['token'],));return self.send(200,{'ok':True},{'Set-Cookie':COOKIE+'=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
    if self.path=='/api/invitations':
     if not is_owner(u):return self.send(403,{'error':'Only the DigitalBurj HQ owner can invite staff.'})
     email=str(b.get('email','')).strip().lower();role=b.get('role');dept=b.get('department')
     if '@' not in email or len(email)>254 or role not in ROLES or dept not in DEPTS:raise ValueError('Enter a valid email, role and department.')
     if c.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():raise ValueError('This staff account already exists.')
     token=secrets.token_urlsafe(32);c.execute('INSERT INTO invitations VALUES(?,?,?,?,?,0)',(hashlib.sha256(token.encode()).hexdigest(),email,role,dept,time.time()+172800));audit(c,u['id'],'Created staff invitation',email)
     if account_mail.enabled():account_mail.queue(c,email,'DigitalBurj staff invitation','Accept your single-use invitation within 48 hours: '+integrations.base()+'/?invite='+token)
     return self.send(201,{'token':token,'expires':'48 hours'})
    if self.path=='/api/staff':
     if not is_owner(u):return self.send(403,{'error':'Only the HQ owner can change staff access.'})
     uid=b.get('id');active=1 if b.get('active') else 0
     target=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
     if not target:raise ValueError('Staff account not found.')
     if target['email']==OWNER_EMAIL:raise ValueError('The owner account cannot be changed through staff management.')
     role=b.get('role',target['role']);department=b.get('department',target['department'])
     if role not in ROLES or department not in DEPTS:raise ValueError('Select a valid role and department.')
     new_password=str(b.get('new_password',''))
     if new_password and len(new_password)<12:raise ValueError('Temporary passwords must contain at least 12 characters.')
     if new_password:c.execute('UPDATE users SET password=? WHERE id=?',(pw_hash(new_password),uid))
     c.execute('UPDATE users SET active=?,role=?,department=? WHERE id=?',(active,role,department,uid));c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));audit(c,u['id'],'Changed staff access',uid);return self.send(200,{'ok':True})
    return self.send(404,{'error':'Not found'})
  except (ValueError,TypeError,json.JSONDecodeError) as e:self.send(400,{'error':str(e)})
  except PermissionError as e:self.send(403,{'error':str(e) or 'This action has not been assigned to your account.'})
  except r2.StorageError as e:self.send(502,{'error':'Document storage is unavailable. '+str(e)})
  except Exception as e:
   if database.integrity_error(e):return self.send(409,{'error':'This record already exists or references an unavailable account.'})
   logging.error('HQ request failed: %s',type(e).__name__)
   self.send(500,{'error':'Request failed. Contact your HQ administrator.'})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8080);p.add_argument('--host',default='127.0.0.1');p.add_argument('--create-admin',action='store_true');a=p.parse_args();init()
 if a.create_admin:
  with connection() as c:
   if c.execute('SELECT 1 FROM users LIMIT 1').fetchone():raise SystemExit('Owner already configured. Use the owner account to invite staff.')
  import getpass
  email=input('Admin email: ').strip().lower();name=input('Admin name: ').strip();password=getpass.getpass('Password (12+ characters): ')
  if email!=OWNER_EMAIL or not name or len(password)<12:raise SystemExit('Use the configured owner email and a 12+ character password.')
  with connection() as c:c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',(secrets.token_hex(12),name,email,pw_hash(password),'admin','Business OS'))
  print('Administrator created.')
 else:
  print(f'DigitalBurj HQ: http://{a.host}:{a.port}');ThreadingHTTPServer((a.host,a.port),Handler).serve_forever()
