import json,os,pathlib,tempfile,unittest,urllib.parse
from unittest.mock import patch
from cryptography.fernet import Fernet
import account_mail,auth_security,database,production,secrets_store,server,test_support
from test_integrations import Response
class ProductionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old_db=server.DB;self.old_boot=server.BOOTSTRAP;server.DB=pathlib.Path(self.tmp.name)/'test.sqlite3';server.BOOTSTRAP=pathlib.Path(self.tmp.name)/'none';test_support.prepare(server);server.init()
 def tearDown(self):server.DB=self.old_db;server.BOOTSTRAP=self.old_boot;self.tmp.cleanup()
 def test_production_rejects_missing_database(self):
  with patch.dict(os.environ,{'HQ_ENV':'production','DATABASE_URL':''}):
   with self.assertRaises(RuntimeError):server.connection()
 def test_owner_totp_rfc_vector(self):
  with patch.dict(os.environ,{'HQ_OWNER_TOTP_SECRET':'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'}):
   self.assertTrue(auth_security.verify_totp('287082',at=59));self.assertFalse(auth_security.verify_totp('000000',at=59))
 def test_encrypted_external_token(self):
  with patch.dict(os.environ,{'HQ_TOKEN_ENCRYPTION_KEY':Fernet.generate_key().decode()}),server.connection() as c:
   secrets_store.put(c,'google',{'refresh_token':'private-test-token'});raw=c.execute("SELECT encrypted FROM service_tokens WHERE name='google'").fetchone()[0];self.assertNotIn('private-test-token',raw);self.assertEqual(secrets_store.get(c,'google')['refresh_token'],'private-test-token');secrets_store.delete(c,'google');self.assertIsNone(secrets_store.get(c,'google'))
 def test_recovery_single_use_and_session_revocation(self):
  with patch.dict(os.environ,{'HQ_TOKEN_ENCRYPTION_KEY':Fernet.generate_key().decode(),'SMTP_HOST':'smtp.example.invalid','SMTP_FROM':'hq@example.invalid'}),server.connection() as c:
   c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',('u','User','u@example.invalid',server.pw_hash('old-test-password'),'developer','Business OS'))
   c.execute('INSERT INTO sessions VALUES(?,?,?,?)',('session','u','csrf',9999999999))
   h=Response('/api/account/recover');account_mail.post(h,c,{'email':'u@example.invalid'},server.pw_hash);self.assertEqual(h.status,200)
   ciphertext=c.execute('SELECT encrypted FROM mail_outbox').fetchone()[0];body=json.loads(secrets_store.cipher().decrypt(ciphertext.encode()))['body'];token=urllib.parse.parse_qs(urllib.parse.urlsplit(body.splitlines()[1]).query)['token'][0]
   h=Response('/api/account/reset');account_mail.post(h,c,{'token':token,'password':'new-test-password'},server.pw_hash);self.assertEqual(c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],0);self.assertTrue(server.pw_ok('new-test-password',c.execute("SELECT password FROM users WHERE id='u'").fetchone()[0]))
   with self.assertRaises(ValueError):account_mail.post(h,c,{'token':token,'password':'again-test-password'},server.pw_hash)
 @unittest.skipUnless(os.environ.get('HQ_TEST_POSTGRES')=='1','Disposable PostgreSQL only')
 def test_postgres_private_schema_and_rls(self):
  import psycopg
  with server.connection() as c:
   schema=database.schema_for(server.DB)
   self.assertEqual(c.execute('SELECT COUNT(*) FROM pg_tables WHERE schemaname=? AND rowsecurity',(schema,)).fetchone()[0],len(json.loads((pathlib.Path(__file__).parent/'sql/tables.json').read_text())))
   c.execute('SET LOCAL ROLE digitalburj_app');self.assertEqual(c.execute('SELECT version FROM schema_version').fetchone()[0],1);c.execute('SET LOCAL ROLE NONE')
   if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='hq_test_anon'").fetchone():c.execute('CREATE ROLE hq_test_anon NOLOGIN')
  with self.assertRaises(psycopg.errors.InsufficientPrivilege):
   with server.connection() as c:
    c.execute('SET LOCAL ROLE hq_test_anon');c.execute('SELECT * FROM '+schema+'.users').fetchall()
 def test_wsgi_transaction_and_host(self):
  with patch.dict(os.environ,{'HQ_PUBLIC_URL':'http://localhost','HQ_ENV':'development'}):
   app=production.create_app();client=app.test_client();self.assertEqual(client.get('/healthz').status_code,200);self.assertEqual(client.get('/readyz').status_code,200);self.assertEqual(client.get('/healthz',headers={'Host':'wrong.example'}).status_code,400);self.assertEqual(client.get('/healthz',headers={'Host':'healthcheck.railway.app'}).status_code,200);self.assertEqual(client.get('/readyz',headers={'Host':'healthcheck.railway.app'}).status_code,400)
   self.assertEqual(client.post('/api/login',json={'email':'absent@example.invalid','password':'test-password-123'}).status_code,401)
   with server.connection() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],1)
 def test_failed_commit_does_not_report_login_success(self):
  import contextlib
  with server.connection() as c:c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',('u','U','u@example.invalid',server.pw_hash('test-password-123'),'developer','Business OS'))
  with patch.dict(os.environ,{'HQ_PUBLIC_URL':'http://localhost','HQ_ENV':'development'}):
   client=production.create_app().test_client();real=server.connection
   @contextlib.contextmanager
   def failed_commit():
    with real() as c:
     yield c
     raise RuntimeError('simulated commit failure')
   with patch.object(server,'connection',failed_commit):
    response=client.post('/api/login',json={'email':'u@example.invalid','password':'test-password-123'})
    self.assertEqual(response.status_code,500);self.assertIn('error',response.get_json());self.assertNotIn('user',response.get_json())
   with real() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],0)
if __name__=='__main__':unittest.main()
