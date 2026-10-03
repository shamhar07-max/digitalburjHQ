import hashlib,hmac,json,os,sqlite3,tempfile,time,unittest
from unittest.mock import patch
import server
import test_support,integrations
class Response:
 def __init__(self,path,headers=None):self.path=path;self.headers=headers or {};self.client_address=('test',0);self.status=None
 def send(self,status,data=None,headers=None):self.status=status;self.data=data or {};self.output_headers=headers or {}
class IntegrationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old_db=server.DB;self.old_boot=server.BOOTSTRAP;server.DB=server.pathlib.Path(self.temp.name)/'test.sqlite3';server.BOOTSTRAP=server.pathlib.Path(self.temp.name)/'none';test_support.prepare(server);server.init();self.c=server.connection()
  self.c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',('owner','Owner',server.OWNER_EMAIL,server.pw_hash('test-password-123'),'admin','Business OS'));self.c.commit()
 def tearDown(self):self.c.close();server.DB=self.old_db;server.BOOTSTRAP=self.old_boot;self.temp.cleanup()
 def test_partner_isolation_signup_login(self):
  h=Response('/api/partner/signup');b={'email':'p@example.com','password':'test-password-123','name':'Partner','program':'Referral','terms':True};integrations.post(h,self.c,b,b'',server.pw_hash,server.pw_ok);self.assertEqual(h.status,201);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)
  h=Response('/api/partner/login');integrations.post(h,self.c,b,b'',server.pw_hash,server.pw_ok);self.assertEqual(h.status,200);cookie=h.output_headers['Set-Cookie'].split(';')[0];h=Response('/api/partner/me',{'Cookie':cookie});integrations.get(h,self.c,None,None);self.assertEqual(h.data['partner']['email'],b['email']);self.assertEqual(h.data['sales'],[])
 def test_signed_division_event_and_scoped_read(self):
  b={'department':'Academy','kind':'learner','event_id':'evt1','external_id':'learn1','data':{'name':'Student'}};raw=json.dumps(b).encode();ts=str(int(time.time()));sig=hmac.new(b'secret',ts.encode()+b'.'+raw,hashlib.sha256).hexdigest()
  with patch.dict(os.environ,{'ACADEMY_WEBHOOK_SECRET':'secret'}):
   h=Response('/api/division/events',{'X-DB-Timestamp':ts,'X-DB-Signature':'wrong'});integrations.post(h,self.c,b,raw,server.pw_hash,server.pw_ok);self.assertEqual(h.status,403)
   h.headers['X-DB-Signature']=sig;integrations.post(h,self.c,b,raw,server.pw_hash,server.pw_ok);self.assertEqual(h.status,200);integrations.post(h,self.c,b,raw,server.pw_hash,server.pw_ok);self.assertTrue(h.data['duplicate'])
  self.c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',('teacher','T','t@example.com',server.pw_hash('test-password-123'),'teacher','Academy'));u=self.c.execute("SELECT * FROM users WHERE id='teacher'").fetchone();h=Response('/api/integrations');integrations.get(h,self.c,u,None);self.assertEqual(h.data['records'],[])
  self.c.execute('INSERT INTO grants VALUES(?,?,?,?,?,?)',('g','teacher','learners.view','department','Academy',server.stamp()));integrations.get(h,self.c,u,None);self.assertEqual(len(h.data['records']),1)
 def test_stripe_verified_idempotent_fulfillment_and_refund(self):
  self.c.execute("INSERT INTO affiliates(id,name,email,program,owner,status,training,code,created) VALUES('p','P','p@example.com','Referral','owner','Active',1,'DB-P',?)",(server.stamp(),))
  self.c.execute("INSERT INTO commerce_orders(id,email,product,net_cents,currency,affiliate_id,status,provider_id,created) VALUES('o','customer@example.com','Academy',10000,'aed','p','Pending','cs_1',?)",(server.stamp(),))
  def event(e):
   raw=json.dumps(e).encode();ts=str(int(time.time()));sig=hmac.new(b'whsec',ts.encode()+b'.'+raw,hashlib.sha256).hexdigest();h=Response('/api/stripe/webhook',{'Stripe-Signature':'t='+ts+',v1='+sig});integrations.stripe_event(h,self.c,e,raw);return h
  with patch.dict(os.environ,{'STRIPE_WEBHOOK_SECRET':'whsec'}):
   e={'id':'evt_paid','type':'checkout.session.completed','data':{'object':{'id':'cs_1','payment_intent':'pi_1','payment_status':'paid','amount_total':10000,'currency':'aed'}}};self.assertEqual(event(e).status,200);self.assertTrue(event(e).data['duplicate']);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM affiliate_sales').fetchone()[0],1);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM division_records').fetchone()[0],2)
   self.assertEqual(event({'id':'evt_refund','type':'charge.refunded','data':{'object':{'payment_intent':'pi_1'}}}).status,200);self.assertEqual(self.c.execute('SELECT status FROM affiliate_sales').fetchone()[0],'Reversed')
 def test_oauth_owner_only_and_state(self):
  u=self.c.execute("SELECT * FROM users WHERE id='owner'").fetchone();h=Response('/api/google/connect');h.user=lambda c:(u,{'token':'bound-session'})
  with patch.dict(os.environ,{'GOOGLE_CLIENT_ID':'client','GOOGLE_CLIENT_SECRET':'secret'}):
   integrations.owner_post(h,self.c,u,{});self.assertIn('state=',h.data['url']);self.assertEqual(self.c.execute('SELECT session_token FROM oauth_states').fetchone()[0],'bound-session')
  h=Response('/api/google/callback?state=bad&code=bad');integrations.get(h,self.c,u,{'token':'bound-session'});self.assertEqual(h.status,403)
if __name__=='__main__':unittest.main()
