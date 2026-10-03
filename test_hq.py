import http.cookiejar,json,os,pathlib,socket,subprocess,tempfile,time,unittest,urllib.request,urllib.error
import server
import test_support
class HQTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();server.DB=pathlib.Path(cls.tmp.name)/'test.sqlite3';server.BOOTSTRAP=pathlib.Path(cls.tmp.name)/'disabled.json';test_support.prepare(server);server.init()
  with server.connection() as c:
   for uid,email,role,dept in [('admin','shamhar07@gmail.com','admin','Business OS'),('teacher','teacher@test.invalid','teacher','Academy'),('otheradmin','otheradmin@test.invalid','admin','Studio')]:c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',(uid,uid,email,server.pw_hash('testing-password-123'),role,dept))
   for permission,scope,scope_id in [('tasks.view','assigned',''),('tasks.update','assigned',''),('tasks.comment','assigned',''),('reviews.view','assigned',''),('reviews.submit','department','Academy'),('notifications.view','assigned',''),('messages.use','department','Academy'),('meetings.view','assigned','')]:c.execute('INSERT INTO grants VALUES(?,?,?,?,?,?)',(server.secrets.token_hex(12),'teacher',permission,scope,scope_id,server.stamp()))
  sock=socket.socket();sock.bind(('127.0.0.1',0));cls.port=sock.getsockname()[1];sock.close();cls.base=f'http://127.0.0.1:{cls.port}'
  cls.proc=subprocess.Popen(['python3','server.py','--port',str(cls.port)],env={**os.environ,'HQ_DB':str(server.DB),'HQ_BOOTSTRAP':str(server.BOOTSTRAP)},stdout=subprocess.DEVNULL)
  for _ in range(50):
   try:urllib.request.urlopen(cls.base);break
   except Exception:time.sleep(.1)
 @classmethod
 def tearDownClass(cls):cls.proc.terminate();cls.proc.wait();cls.tmp.cleanup()
 def request(self,op,path,data=None,csrf=''):
  req=urllib.request.Request(self.base+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
  try:r=op.open(req)
  except urllib.error.HTTPError as e:r=e
  return r.code,json.loads(r.read())
 def client(self,email):
  op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));status,data=self.request(op,'login',{'email':email,'password':'testing-password-123'});self.assertEqual(status,200);return op,data['csrf']
 def test_workflow_and_department_isolation(self):
  admin,ac=self.client('shamhar07@gmail.com');teacher,tc=self.client('teacher@test.invalid')
  status,t=self.request(admin,'tasks',{'title':'Private product task','department':'Business OS','priority':'High'},ac);self.assertEqual(status,200)
  status,a=self.request(admin,'tasks',{'title':'Teach assessment','department':'Academy','owner':'teacher'},ac);self.assertEqual(status,200)
  _,workspace=self.request(teacher,'workspace');self.assertIn('Teach assessment',[x['title'] for x in workspace['tasks']]);self.assertNotIn('Private product task',[x['title'] for x in workspace['tasks']])
  self.assertEqual(self.request(teacher,'task-status',{'id':t['id'],'status':'Review'},tc)[0],403)
  self.assertEqual(self.request(teacher,'task-status',{'id':a['id'],'status':'Done'},tc)[0],403)
  self.assertEqual(self.request(teacher,'task-status',{'id':a['id'],'status':'Review'},tc)[0],200)
  self.assertEqual(self.request(admin,'task-status',{'id':a['id'],'status':'Done'},ac)[0],200)
  self.assertEqual(self.request(admin,'tasks',{'title':'No CSRF','department':'Academy'})[0],403)
  other,oc=self.client('otheradmin@test.invalid')
  self.assertEqual(self.request(other,'invitations',{'email':'no@test.invalid','role':'developer','department':'Business OS'},oc)[0],403)
  self.assertEqual(self.request(other,'staff',{'id':'admin','active':False},oc)[0],403)
  self.assertEqual(self.request(teacher,'invitations',{'email':'x@test.invalid','role':'admin','department':'Studio'},tc)[0],403)
  status,invite=self.request(admin,'invitations',{'email':'new@test.invalid','role':'designer','department':'Studio'},ac);self.assertEqual(status,201)
  fresh=urllib.request.build_opener();body={'token':invite['token'],'name':'New designer','password':'secure-password-123'}
  self.assertEqual(self.request(fresh,'accept-invite',body)[0],201);
  _,current=self.request(admin,'workspace');self.assertTrue(current['user']['can_invite']);self.assertFalse(self.request(other,'me')[1]['user']['can_invite'])
  self.assertEqual(self.request(fresh,'accept-invite',body)[0],400)
  status,r=self.request(teacher,'reviews',{'title':'Assessment rubric','department':'Academy','description':'Evidence'},tc);self.assertEqual(status,200)
  self.assertEqual(self.request(teacher,'review-decision',{'id':r['id'],'status':'Approved'},tc)[0],403)
  self.assertEqual(self.request(admin,'review-decision',{'id':r['id'],'status':'Changes requested','feedback':'Add evidence criteria'},ac)[0],200)
  self.assertEqual(self.request(admin,'staff',{'id':'teacher','active':False},ac)[0],200)
  self.assertEqual(self.request(teacher,'workspace')[0],401)
 def test_owner_invites_password_and_revocation(self):
  admin,csrf=self.client('shamhar07@gmail.com');other,oc=self.client('otheradmin@test.invalid')
  status,invite=self.request(admin,'invitations',{'email':'revoke@test.invalid','role':'developer','department':'Business OS'},csrf);self.assertEqual(status,201)
  _,workspace=self.request(admin,'workspace');item=next(x for x in workspace['invitations'] if x['email']=='revoke@test.invalid')
  self.assertEqual(self.request(other,'revoke-invite',{'id':item['id']},oc)[0],403)
  self.assertEqual(self.request(admin,'revoke-invite',{'id':item['id']},csrf)[0],200)
  self.assertEqual(self.request(urllib.request.build_opener(),'accept-invite',{'token':invite['token'],'name':'No','password':'long-password-123'})[0],400)
  second,sc=self.client('otheradmin@test.invalid')
  self.assertEqual(self.request(other,'change-password',{'current':'wrong','password':'new-test-password-123'},oc)[0],400)
  self.assertEqual(self.request(other,'change-password',{'current':'testing-password-123','password':'new-test-password-123'},oc)[0],200)
  self.assertEqual(self.request(second,'workspace')[0],401)
  self.assertEqual(self.request(other,'workspace')[0],200)
  self.assertEqual(self.request(other,'change-password',{'current':'new-test-password-123','password':'testing-password-123'},oc)[0],200)
 def test_record_access_and_immediate_revocation(self):
  admin,ac=self.client('shamhar07@gmail.com');teacher,tc=self.client('teacher@test.invalid')
  _,a=self.request(admin,'tasks',{'title':'Only this exact job','department':'Academy','owner':'teacher'},ac)
  _,b=self.request(admin,'tasks',{'title':'Same person, different job','department':'Academy','owner':'teacher'},ac)
  grants=[{'permission':p,'scope_type':'record','scope_id':a['id']} for p in ['tasks.view','tasks.update','tasks.comment']]
  self.assertEqual(self.request(admin,'permissions',{'user_id':'teacher','grants':grants},ac)[0],200)
  _,w=self.request(teacher,'workspace');self.assertEqual([t['id'] for t in w['tasks']],[a['id']]);self.assertEqual(w['staff'][0]['id'],'teacher');self.assertEqual(w['affiliates'],[])
  self.assertEqual(self.request(teacher,'task-status',{'id':b['id'],'status':'Review'},tc)[0],403)
  self.assertEqual(self.request(teacher,'permissions',{'user_id':'teacher','grants':[{'permission':'audit.view','scope_type':'all','scope_id':''}]},tc)[0],403)
  self.assertEqual(self.request(teacher,'task-comment',{'id':a['id'],'body':'Evidence ready'},tc)[0],200)
  self.assertEqual(self.request(admin,'permissions',{'user_id':'teacher','grants':[]},ac)[0],200)
  self.assertEqual(self.request(teacher,'task-status',{'id':a['id'],'status':'Review'},tc)[0],403)
  _,w=self.request(teacher,'workspace');self.assertEqual(w['tasks'],[]);self.assertEqual(w['comments'],[])
  with server.connection() as c:
   for permission,scope,scope_id in [('tasks.view','assigned',''),('tasks.update','assigned',''),('tasks.comment','assigned',''),('reviews.view','assigned',''),('reviews.submit','department','Academy'),('notifications.view','assigned',''),('messages.use','department','Academy'),('meetings.view','assigned','')]:c.execute('INSERT INTO grants VALUES(?,?,?,?,?,?)',(server.secrets.token_hex(12),'teacher',permission,scope,scope_id,server.stamp()))
 def test_messages_notifications_meetings_and_affiliates(self):
  admin,ac=self.client('shamhar07@gmail.com');teacher,tc=self.client('teacher@test.invalid');other,oc=self.client('otheradmin@test.invalid')
  self.assertEqual(self.request(teacher,'messages',{'recipient':'otheradmin','body':'Outside scope'},tc)[0],403)
  self.assertEqual(self.request(admin,'messages',{'recipient':'teacher','body':'Please review your assigned job'},ac)[0],200)
  _,w=self.request(teacher,'workspace');self.assertGreaterEqual(w['unread_messages'],1);self.assertGreaterEqual(w['unread_notifications'],1)
  _,hidden=self.request(other,'workspace');self.assertEqual(hidden['messages'],[]);self.assertEqual(hidden['notifications'],[])
  self.assertEqual(self.request(teacher,'message-read',{'sender':'admin'},tc)[0],200)
  self.assertEqual(self.request(teacher,'workspace')[1]['unread_messages'],0)
  start='2027-01-04T09:00:00+04:00';end='2027-01-04T09:30:00+04:00'
  _,meeting=self.request(admin,'meetings',{'title':'Assigned staff call','department':'Academy','starts':start,'ends':end,'url':'https://meet.google.com/abc-defg-hij','participants':['teacher']},ac)
  self.assertIn(meeting['id'],[m['id'] for m in self.request(teacher,'workspace')[1]['meetings']]);self.assertEqual(self.request(other,'workspace')[1]['meetings'],[])
  self.assertEqual(self.request(teacher,'meeting-status',{'id':meeting['id'],'status':'Cancelled'},tc)[0],403)
  self.assertEqual(self.request(admin,'meetings',{'title':'Invalid URL','department':'Academy','starts':start,'ends':end,'url':'javascript:alert(1)'},ac)[0],400)
  _,partner=self.request(admin,'affiliates',{'name':'Test partner','email':'partner@test.invalid','program':'Referral','owner':'admin'},ac)
  aid=partner['id'];self.assertEqual(self.request(admin,'affiliate-update',{'id':aid,'status':'Active','training':True},ac)[0],200)
  self.assertEqual(self.request(teacher,'affiliate-sales',{'id':aid},tc)[0],403)
  body={'id':aid,'invoice':'INV-test-1','customer':'CUST-1','product':'Academy','net_cents':100000,'clear_on':'2026-01-01','evidence':'Receipt 123','verified_by':'Owner'}
  status,sale=self.request(admin,'affiliate-sales',body,ac);self.assertEqual(status,200);self.assertEqual(sale['commission_cents'],15000)
  self.assertEqual(self.request(admin,'affiliate-sales',body,ac)[0],409)
  self.assertEqual(self.request(admin,'affiliate-qualify',{'id':aid},ac)[0],400)
  self.assertEqual(self.request(admin,'commission-status',{'id':sale['id'],'status':'Approved'},ac)[0],200)
  self.assertEqual(self.request(admin,'affiliate-qualify',{'id':aid},ac)[0],200)
  self.assertEqual(self.request(admin,'commission-payout',{'id':sale['id'],'payout_ref':'BANK-123'},ac)[0],200)
  self.assertEqual(self.request(admin,'commission-status',{'id':sale['id'],'status':'Reversed','reason':'After paid'},ac)[0],400)
 def test_subscription_caps_rate_snapshots_and_policy_permissions(self):
  admin,ac=self.client('shamhar07@gmail.com');other,oc=self.client('otheradmin@test.invalid')
  _,a=self.request(admin,'affiliates',{'name':'Subscription partner','email':'subscription@test.invalid','program':'Sales','owner':'admin'},ac);aid=a['id']
  self.request(admin,'affiliate-update',{'id':aid,'status':'Active','training':True},ac)
  body={'id':aid,'invoice':'SUB-1','customer':'SUB-CUST','product':'Business','net_cents':100000,'months':1,'clear_on':'2026-01-01','evidence':'Receipt','verified_by':'Owner'}
  status,first=self.request(admin,'affiliate-sales',body,ac);self.assertEqual(status,200);self.assertEqual(first['rate_bps'],1000)
  policy={'rates':{'Business':[3000,3500,4000],'Academy':[1500,2000,2500],'Studio':[800,1000,1200]},'founding_rates':{'Business':4000,'Academy':2500,'Studio':1200}}
  self.assertEqual(self.request(other,'programme-policy',{'policy':policy},oc)[0],403)
  self.assertEqual(self.request(admin,'programme-policy',{'policy':policy},ac)[0],200)
  _,second=self.request(admin,'affiliate-sales',{**body,'invoice':'SUB-2','months':11},ac);self.assertEqual(second['rate_bps'],1000)
  self.assertEqual(self.request(admin,'affiliate-sales',{**body,'invoice':'SUB-3'},ac)[0],400)
  _,new=self.request(admin,'affiliate-sales',{**body,'invoice':'SUB-new','customer':'NEW-CUST'},ac);self.assertEqual(new['rate_bps'],3000)
  status,held=self.request(admin,'affiliate-sales',{**body,'invoice':'SUB-held','customer':'HELD-CUST','clear_on':'2099-01-01'},ac);self.assertEqual(status,200)
  self.assertEqual(self.request(admin,'commission-status',{'id':held['id'],'status':'Approved'},ac)[0],400)
  import hq_features
  self.request(admin,'programme-policy',{'policy':hq_features.DEFAULT_POLICY},ac)
 def test_unauthenticated(self):self.assertEqual(self.request(urllib.request.build_opener(),'workspace')[0],401)
if __name__=='__main__':unittest.main()
