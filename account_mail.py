"""Verified SMTP outbox and single-use email verification/password recovery."""
import datetime,hashlib,hmac,json,os,secrets,smtplib,ssl,time
from email.message import EmailMessage
import hq_features as f
import secrets_store

def init(c):
 c.executescript('''
 CREATE TABLE IF NOT EXISTS account_tokens(token TEXT PRIMARY KEY,kind TEXT,account_id TEXT,expires DOUBLE PRECISION,used INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS mail_outbox(id TEXT PRIMARY KEY,recipient TEXT,encrypted TEXT,attempts INTEGER NOT NULL DEFAULT 0,next_at DOUBLE PRECISION,sent TEXT,created TEXT);
 ''')
 if 'verified' not in [r[1] for r in c.execute('PRAGMA table_info(partner_accounts)')]:c.execute('ALTER TABLE partner_accounts ADD COLUMN verified INTEGER NOT NULL DEFAULT 0')
def enabled():return bool(os.environ.get('SMTP_HOST') and os.environ.get('SMTP_FROM'))
def queue(c,to,subject,body):
 encrypted=secrets_store.cipher().encrypt(json.dumps({'subject':subject,'body':body}).encode()).decode()
 c.execute('INSERT INTO mail_outbox VALUES(?,?,?,0,?,NULL,?)',(f.uid(),to,encrypted,time.time(),f.now()))
def issue(c,to,kind,account):
 import integrations
 token=secrets.token_urlsafe(32);c.execute('INSERT INTO account_tokens VALUES(?,?,?,?,0)',(hashlib.sha256(token.encode()).hexdigest(),kind,account,time.time()+1800))
 url=integrations.base()+'/account.html?token='+token+'&action='+('verify' if kind=='verify' else 'reset')
 queue(c,to,'DigitalBurj account '+('verification' if kind=='verify' else 'recovery'),'Use this single-use link within 30 minutes:\n'+url+'\nIf you did not request this, ignore this email.')
def limited(c,h):
 key='recovery:'+h.client_address[0];row=c.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone();now=time.time()
 if row and row['until']>now and row['count']>=5:return True
 count=row['count']+1 if row and row['until']>now else 1
 c.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(key,count,now+900));return False

def post(h,c,b,pw_hash):
 if h.path not in ['/api/account/recover','/api/account/resend','/api/account/reset','/api/account/verify']:return False
 if h.path.endswith(('recover','resend')):
  if limited(c,h):h.send(429,{'error':'Try again in 15 minutes.'});return True
  if not enabled():raise ValueError('Email recovery is not configured. Contact the HQ owner.')
  email=str(b.get('email','')).strip().lower()[:254]
  if h.path.endswith('resend'):
   partner=c.execute('SELECT p.id,p.verified FROM partner_accounts p JOIN affiliates a ON a.id=p.id WHERE a.email=?',(email,)).fetchone()
   if partner and not partner['verified']:issue(c,email,'verify',partner['id'])
  else:
   staff=c.execute('SELECT id FROM users WHERE email=? AND active=1',(email,)).fetchone()
   partner=c.execute('SELECT p.id FROM partner_accounts p JOIN affiliates a ON a.id=p.id WHERE a.email=?',(email,)).fetchone()
   if staff:issue(c,email,'staff_reset',staff['id'])
   elif partner:issue(c,email,'partner_reset',partner['id'])
  h.send(200,{'ok':True,'message':'If an eligible account exists, an email will be sent.'});return True
 token=hashlib.sha256(str(b.get('token','')).encode()).hexdigest();row=c.execute('SELECT * FROM account_tokens WHERE token=? AND used=0 AND expires>?',(token,time.time())).fetchone()
 if not row:raise ValueError('This link is invalid, expired or already used.')
 if h.path.endswith('verify'):
  if row['kind']!='verify':raise ValueError('Invalid verification link.')
  c.execute('UPDATE partner_accounts SET verified=1 WHERE id=?',(row['account_id'],))
 else:
  if row['kind'] not in ['staff_reset','partner_reset']:raise ValueError('Invalid recovery link.')
  password=str(b.get('password',''))
  if not 12<=len(password)<=256:raise ValueError('Use a password between 12 and 256 characters.')
  table='users' if row['kind']=='staff_reset' else 'partner_accounts'
  c.execute('UPDATE '+table+' SET password=? WHERE id=?',(pw_hash(password),row['account_id']))
  c.execute('DELETE FROM '+('sessions WHERE user_id=?' if table=='users' else 'partner_sessions WHERE partner_id=?'),(row['account_id'],))
 c.execute('UPDATE account_tokens SET used=1 WHERE account_id=? AND kind=?',(row['account_id'],row['kind']));h.send(200,{'ok':True});return True

def deliver(c):
 row=c.execute('SELECT * FROM mail_outbox WHERE sent IS NULL AND attempts<6 AND next_at<=? ORDER BY created LIMIT 1',(time.time(),)).fetchone()
 if not row:return False
 if c.is_postgres:
  # Serialize outbox workers and recheck after taking the transaction lock.
  c.execute('SELECT pg_advisory_xact_lock(72844003)')
  row=c.execute('SELECT * FROM mail_outbox WHERE sent IS NULL AND attempts<6 AND next_at<=? ORDER BY created LIMIT 1',(time.time(),)).fetchone()
  if not row:return False
 data=json.loads(secrets_store.cipher().decrypt(row['encrypted'].encode()));message=EmailMessage();message['From']=os.environ['SMTP_FROM'];message['To']=row['recipient'];message['Subject']=data['subject'];message.set_content(data['body'])
 try:
  port=int(os.environ.get('SMTP_PORT','587'));context=ssl.create_default_context()
  smtp=smtplib.SMTP_SSL(os.environ['SMTP_HOST'],port,timeout=20,context=context) if port==465 else smtplib.SMTP(os.environ['SMTP_HOST'],port,timeout=20)
  with smtp:
   if port!=465:smtp.starttls(context=context)
   if os.environ.get('SMTP_USER'):smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
   smtp.send_message(message)
  c.execute('UPDATE mail_outbox SET sent=?,encrypted=? WHERE id=?',(f.now(),'sent',row['id']))
 except Exception:
  attempts=row['attempts']+1;c.execute('UPDATE mail_outbox SET attempts=?,next_at=? WHERE id=?',(attempts,time.time()+min(3600,60*2**attempts),row['id']))
 return True
