"""Partner portal, Google OAuth and authenticated division/payment ingestion."""
import datetime, hashlib, hmac, http.cookies, json, os, pathlib, re, secrets, time, urllib.parse, urllib.request
import hq_features as f
COOKIE='db_partner_session'
PROGRAMS=['Referral','Sales','Creator','Campus','Agency']
def init(c):
 c.executescript('''
 CREATE TABLE IF NOT EXISTS partner_accounts(id TEXT PRIMARY KEY REFERENCES affiliates(id),password TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS partner_sessions(token TEXT PRIMARY KEY,partner_id TEXT REFERENCES affiliates(id),csrf TEXT,expires REAL);
 CREATE TABLE IF NOT EXISTS oauth_states(state TEXT PRIMARY KEY,user_id TEXT,session_token TEXT,expires REAL);
 CREATE TABLE IF NOT EXISTS integration_events(source TEXT,event_id TEXT,payload_hash TEXT,created TEXT,PRIMARY KEY(source,event_id));
 CREATE TABLE IF NOT EXISTS division_records(id TEXT PRIMARY KEY,department TEXT,kind TEXT,external_id TEXT,data TEXT,created TEXT,UNIQUE(department,kind,external_id));
 CREATE TABLE IF NOT EXISTS commerce_orders(id TEXT PRIMARY KEY,email TEXT,product TEXT,net_cents INTEGER,currency TEXT,affiliate_id TEXT REFERENCES affiliates(id),status TEXT,provider_id TEXT UNIQUE,created TEXT);
 ''')
 if 'payment_intent' not in [r[1] for r in c.execute('PRAGMA table_info(commerce_orders)')]:c.execute("ALTER TABLE commerce_orders ADD COLUMN payment_intent TEXT")
 for key,label in [('customers.view','View customer records'),('learners.view','View learner records'),('payments.view','View payment records')]:f.PERMISSIONS[key]=label

def base():
 value=os.environ.get('HQ_PUBLIC_URL','http://127.0.0.1:8080').rstrip('/')
 if not value.startswith(('https://','http://127.0.0.1:','http://localhost:')):raise ValueError('Configure HQ_PUBLIC_URL with HTTPS.')
 return value

def tokens_path():return pathlib.Path(os.environ.get('HQ_GOOGLE_TOKEN_FILE',str(pathlib.Path(__file__).parent/'private/google.json')))
def google_connected():return tokens_path().is_file() or bool(os.environ.get('GOOGLE_MEET_ACCESS_TOKEN') or os.environ.get('GOOGLE_REFRESH_TOKEN'))
def google_token():
 p=tokens_path()
 if not p.is_file():return None
 token=json.loads(p.read_text()).get('refresh_token')
 if not token:raise ValueError('Reconnect Google to grant offline access.')
 return request('https://oauth2.googleapis.com/token',{'client_id':os.environ['GOOGLE_CLIENT_ID'],'client_secret':os.environ['GOOGLE_CLIENT_SECRET'],'refresh_token':token,'grant_type':'refresh_token'})['access_token']
def request(url,data,headers=None):
 req=urllib.request.Request(url,data=urllib.parse.urlencode(data).encode(),headers=headers or {})
 try:
  with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
 except Exception:raise ValueError('External service request failed. Check the connection credentials.')

def partner(c,h):
 cookies=http.cookies.SimpleCookie(h.headers.get('Cookie',''));t=cookies.get(COOKIE)
 return c.execute('SELECT s.*,a.name,a.email,a.status,a.code FROM partner_sessions s JOIN affiliates a ON a.id=s.partner_id WHERE s.token=? AND s.expires>?',(hashlib.sha256(t.value.encode()).hexdigest(),time.time())).fetchone() if t else None

def get(h,c,u,s):
 path=urllib.parse.urlsplit(h.path);q=urllib.parse.parse_qs(path.query)
 if path.path=='/api/partner/me':
  p=partner(c,h)
  if not p:h.send(401,{'error':'Sign in to your partner account.'});return True
  a=dict(c.execute('SELECT * FROM affiliates WHERE id=?',(p['partner_id'],)).fetchone())
  sales=[{k:r[k] for k in ['id','product','net_cents','rate_bps','commission_cents','status','created']} for r in c.execute('SELECT * FROM affiliate_sales WHERE affiliate_id=?',(p['partner_id'],))]
  h.send(200,{'partner':a,'sales':sales,'csrf':p['csrf'],'referral_url':base()+'/partners.html?ref='+a['code']});return True
 if path.path=='/api/integrations':
  if not u:h.send(401);return True
  records=[]
  for r in c.execute('SELECT * FROM division_records ORDER BY created DESC LIMIT 1000'):
   permission={'learner':'learners.view','customer':'customers.view','payment':'payments.view'}[r['kind']]
   if f.has(c,u,permission,r['department'],r['id']):records.append({**dict(r),'data':json.loads(r['data'])})
  h.send(200,{'records':records,'owner':f.owner(u),'google_connected':google_connected(),'google_configured':bool(os.environ.get('GOOGLE_CLIENT_ID') and os.environ.get('GOOGLE_CLIENT_SECRET')),'stripe_configured':bool(os.environ.get('STRIPE_SECRET_KEY') and os.environ.get('STRIPE_WEBHOOK_SECRET'))});return True
 if path.path=='/api/google/callback':
  if not u or not f.owner(u):h.send(403);return True
  state=q.get('state',[''])[0];row=c.execute('SELECT * FROM oauth_states WHERE state=? AND expires>?',(hashlib.sha256(state.encode()).hexdigest(),time.time())).fetchone()
  if not row or row['user_id']!=u['id'] or row['session_token']!=s['token']:h.send(403,{'error':'Invalid or expired Google authorization state.'});return True
  c.execute('DELETE FROM oauth_states WHERE state=?',(row['state'],));c.commit()
  if 'error' in q:raise ValueError('Google authorization was declined. Reconnect from HQ.')
  result=request('https://oauth2.googleapis.com/token',{'client_id':os.environ['GOOGLE_CLIENT_ID'],'client_secret':os.environ['GOOGLE_CLIENT_SECRET'],'code':q.get('code',[''])[0],'redirect_uri':base()+'/api/google/callback','grant_type':'authorization_code'})
  if 'https://www.googleapis.com/auth/meetings.space.created' not in result.get('scope','').split():raise ValueError('Google Meet permission was not granted.')
  if not result.get('refresh_token'):raise ValueError('Offline permission was not granted. Reconnect and approve access.')
  p=tokens_path();p.parent.mkdir(parents=True,exist_ok=True);p.parent.chmod(0o700)
  temp=p.with_suffix('.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
  with os.fdopen(fd,'w') as out:json.dump({'refresh_token':result['refresh_token']},out)
  temp.replace(p);f.audit(c,u,'Connected Google Meet','Google');h.send_response(303);h.send_header('Location','/');h.end_headers();return True
 return False

def post(h,c,b,raw,pw_hash,pw_ok):
 path=h.path
 if path in ['/api/partner/signup','/api/partner/login']:
  email=str(b.get('email','')).strip().lower();password=str(b.get('password',''))
  key='partner:'+h.client_address[0];a=c.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone();now=time.time()
  if a and a['until']>now and a['count']>=10:h.send(429,{'error':'Try again in 15 minutes.'});return True
  count=a['count']+1 if a and a['until']>now else 1;c.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(key,count,now+900))
  if path.endswith('signup'):
   if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254 or len(password)<12 or len(password)>256 or b.get('program') not in PROGRAMS or b.get('terms') is not True:raise ValueError('Enter valid details, a 12-character password and accept the programme terms.')
   name=f.clean(b,'name',100);aid=f.uid();c.execute("INSERT INTO affiliates(id,name,email,program,owner,status,training,code,created) VALUES(?,?,?,?,NULL,'Applied',0,?,?)",(aid,name,email,b['program'],'DB-'+secrets.token_hex(4).upper(),f.now()));c.execute('INSERT INTO partner_accounts VALUES(?,?)',(aid,pw_hash(password)))
   for owner in c.execute('SELECT id FROM users WHERE email=?',(f.OWNER,)):f.notify(c,owner['id'],'New affiliate application: '+name)
   h.send(201,{'ok':True});return True
  p=c.execute('SELECT a.*,p.password FROM partner_accounts p JOIN affiliates a ON a.id=p.id WHERE a.email=?',(email,)).fetchone()
  if not p or len(password)>256 or not pw_ok(password,p['password']):h.send(401,{'error':'Email or password is incorrect.'});return True
  token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);c.execute('INSERT INTO partner_sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),p['id'],csrf,now+28800))
  h.send(200,{'csrf':csrf},{'Set-Cookie':COOKIE+'='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+('; Secure' if os.environ.get('HQ_SECURE_COOKIE')=='1' else '')});return True
 if path=='/api/partner/logout':
  p=partner(c,h)
  if not p or not hmac.compare_digest(h.headers.get('X-CSRF-Token',''),p['csrf']):h.send(403);return True
  c.execute('DELETE FROM partner_sessions WHERE token=?',(p['token'],));h.send(200,{'ok':True},{'Set-Cookie':COOKIE+'=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'});return True
 if path=='/api/division/events':
  department=b.get('department');kind=b.get('kind');event=f.clean(b,'event_id',150);external=f.clean(b,'external_id',150)
  secret=os.environ.get({'Academy':'ACADEMY_WEBHOOK_SECRET','Business OS':'BUSINESS_WEBHOOK_SECRET','Studio':'STUDIO_WEBHOOK_SECRET'}.get(department,'INVALID'),'')
  if not secret or kind not in ['customer','learner','payment']:h.send(403);return True
  timestamp=h.headers.get('X-DB-Timestamp','');sig=h.headers.get('X-DB-Signature','')
  if not timestamp.isdigit() or abs(time.time()-int(timestamp))>300 or not hmac.compare_digest(sig,hmac.new(secret.encode(),timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()):h.send(403);return True
  digest=hashlib.sha256(raw).hexdigest();old=c.execute('SELECT payload_hash FROM integration_events WHERE source=? AND event_id=?',(department,event)).fetchone()
  if old:
   h.send(200 if old[0]==digest else 409,{'duplicate':True});return True
  data=b.get('data')
  if not isinstance(data,dict):raise ValueError('data must be an object')
  c.execute('INSERT INTO integration_events VALUES(?,?,?,?)',(department,event,digest,f.now()))
  c.execute('INSERT INTO division_records VALUES(?,?,?,?,?,?) ON CONFLICT(department,kind,external_id) DO UPDATE SET data=excluded.data,created=excluded.created',(f.uid(),department,kind,external,json.dumps(data),f.now()))
  h.send(200,{'ok':True});return True
 return False

def owner_post(h,c,u,b):
 if h.path not in ['/api/google/connect','/api/google/disconnect']:return False
 if not f.owner(u):h.send(403);return True
 if h.path.endswith('disconnect'):
  tokens_path().unlink(missing_ok=True);f.audit(c,u,'Disconnected local Google authorization','Google');h.send(200,{'ok':True});return True
 if not os.environ.get('GOOGLE_CLIENT_ID') or not os.environ.get('GOOGLE_CLIENT_SECRET'):raise ValueError('Configure Google client credentials on the server first.')
 state=secrets.token_urlsafe(32);_,session=h.user(c)
 c.execute('INSERT INTO oauth_states VALUES(?,?,?,?)',(hashlib.sha256(state.encode()).hexdigest(),u['id'],session['token'],time.time()+600))
 h.send(200,{'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode({'client_id':os.environ['GOOGLE_CLIENT_ID'],'redirect_uri':base()+'/api/google/callback','response_type':'code','scope':'https://www.googleapis.com/auth/meetings.space.created','access_type':'offline','prompt':'consent','state':state})});return True

def checkout(h,c,b):
 p=partner(c,h)
 if not p or not hmac.compare_digest(h.headers.get('X-CSRF-Token',''),p['csrf']):h.send(403);return
 product=b.get('product');catalog=json.loads(os.environ.get('HQ_PRODUCT_CATALOG','{}'));item=catalog.get(product)
 if not item or product not in ['Business','Academy','Studio'] or not os.environ.get('STRIPE_SECRET_KEY'):raise ValueError('This product checkout is not configured.')
 amount=item.get('net_cents')
 if type(amount)!=int or amount<=0:raise ValueError('Invalid server product price.')
 if p['status']!='Active':raise ValueError('Your affiliate account must be approved before referring sales.')
 email=f.clean(b,'customer_email',254).lower()
 if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or email==p['email']:raise ValueError('Enter a valid customer email. Self referrals are not eligible.')
 oid=f.uid();a=c.execute('SELECT * FROM affiliates WHERE id=?',(p['partner_id'],)).fetchone()
 data={'mode':'payment','success_url':base()+'/partners.html?checkout=complete','cancel_url':base()+'/partners.html?checkout=cancelled','customer_email':email,'client_reference_id':oid,'metadata[order_id]':oid,'payment_intent_data[metadata][hq_order_id]':oid,'line_items[0][price_data][currency]':'aed','line_items[0][price_data][unit_amount]':amount,'line_items[0][price_data][product_data][name]':item.get('name',product),'line_items[0][quantity]':1}
 r=request('https://api.stripe.com/v1/checkout/sessions',data,{'Authorization':'Bearer '+os.environ['STRIPE_SECRET_KEY']})
 c.execute('INSERT INTO commerce_orders(id,email,product,net_cents,currency,affiliate_id,status,provider_id,created) VALUES(?,?,?,?,?,?,?,?,?)',(oid,email,product,amount,'aed',a['id'],'Pending',r['id'],f.now()));h.send(200,{'url':r['url']})

def stripe_event(h,c,b,raw):
 secret=os.environ.get('STRIPE_WEBHOOK_SECRET','');parts={}
 for part in h.headers.get('Stripe-Signature','').split(','):
  key,sep,value=part.partition('=')
  if sep:parts.setdefault(key,[]).append(value)
 ts=parts.get('t',[''])[0]
 expected=hmac.new(secret.encode(),ts.encode()+b'.'+raw,hashlib.sha256).hexdigest()
 if not secret or not ts.isdigit() or abs(time.time()-int(ts))>300 or not any(hmac.compare_digest(expected,v) for v in parts.get('v1',[])):h.send(400,{'error':'Invalid payment signature.'});return
 event=f.clean(b,'id',150);digest=hashlib.sha256(raw).hexdigest();old=c.execute("SELECT payload_hash FROM integration_events WHERE source='stripe' AND event_id=?",(event,)).fetchone()
 if old:h.send(200 if old[0]==digest else 409,{'duplicate':True});return
 obj=b.get('data',{}).get('object',{});typ=b.get('type')
 if typ in ['checkout.session.completed','checkout.session.async_payment_succeeded'] and obj.get('payment_status')=='paid':
  order=c.execute('SELECT * FROM commerce_orders WHERE provider_id=?',(obj.get('id'),)).fetchone()
  if not order:raise ValueError('Unknown checkout order. No fulfillment performed.')
  if obj.get('currency')!='aed' or obj.get('amount_total')!=order['net_cents']:raise ValueError('Payment does not match the order amount.')
  if order['status']=='Pending':
   owner=c.execute('SELECT * FROM users WHERE email=?',(f.OWNER,)).fetchone()
   if not owner:raise ValueError('HQ owner must be initialized before payment fulfillment.')
   class Recorder:
    path='/api/affiliate-sales'
    def send(self,status,data=None):
     if status>=400:raise ValueError((data or {}).get('error','Commission record failed'))
   f.post(Recorder(),c,owner,{'id':order['affiliate_id'],'invoice':obj['id'],'customer':order['email'],'product':order['product'],'net_cents':order['net_cents'],'clear_on':(datetime.date.today()+datetime.timedelta(days=int(os.environ.get('HQ_REFUND_HOLD_DAYS','14')))).isoformat(),'evidence':'Stripe signed event '+event,'verified_by':'Stripe webhook','months':1})
   c.execute("UPDATE commerce_orders SET status='Paid',payment_intent=? WHERE id=?",(obj.get('payment_intent'),order['id']))
   dept={'Business':'Business OS','Academy':'Academy','Studio':'Studio'}[order['product']]
   for kind in ['payment','learner' if dept=='Academy' else 'customer']:
    payload={'email':order['email'],'product':order['product'],'payment_status':'Paid','order_id':order['id'],'provisioning_status':'Awaiting division fulfillment'}
    c.execute('INSERT OR REPLACE INTO division_records VALUES(?,?,?,?,?,?)',(f.uid(),dept,kind,order['id'],json.dumps(payload),f.now()))
 elif typ=='charge.refunded':
  # Full and partial refunds both stop unpaid commission; paid recoveries need finance review.
  order=c.execute('SELECT provider_id FROM commerce_orders WHERE payment_intent=?',(obj.get('payment_intent'),)).fetchone()
  session_id=order['provider_id'] if order else None
  if session_id:
   c.execute("UPDATE affiliate_sales SET status='Reversed' WHERE invoice=? AND status IN ('Pending','Approved')",(session_id,))
   c.execute("UPDATE commerce_orders SET status='Refunded' WHERE provider_id=?",(session_id,))
  for u in c.execute('SELECT id FROM users WHERE email=?',(f.OWNER,)):f.notify(c,u['id'],'Stripe refund received; review commission recovery and division access. Event '+event)
 c.execute('INSERT INTO integration_events VALUES(?,?,?,?)',('stripe',event,digest,f.now()));h.send(200,{'ok':True})
