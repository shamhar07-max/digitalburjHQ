"""Granular HQ permissions and scoped collaboration/partner operations."""
import datetime,hashlib,json,os,re,secrets,time,urllib.request,urllib.parse,urllib.error
DEPTS=['Business OS','Academy','Studio','Growth']
OWNER='shamhar07@gmail.com'
PERMISSIONS={
 'tasks.view':'View jobs','tasks.create':'Create / assign jobs','tasks.assign':'Edit job brief / assignment','tasks.update':'Update job progress','tasks.approve':'Confirm completed jobs','tasks.comment':'Discuss assigned jobs',
 'reviews.view':'View reviews','reviews.submit':'Submit reviews','reviews.approve':'Approve reviews',
 'people.view':'View staff directory','announcements.view':'Read team announcements','announcements.publish':'Publish announcements',
 'messages.use':'Send and read own messages','notifications.view':'Read own notifications',
 'meetings.view':'View scheduled meetings','meetings.create':'Schedule meetings','meetings.manage':'Change meeting status',
 'resources.view':'Read knowledge resources','resources.update':'Edit assigned resources','resources.manage':'Manage knowledge resources',
 'affiliates.view':'View partner records','affiliates.manage':'Manage partner onboarding','affiliates.qualify':'Confirm founding qualifications',
 'sales.record':'Record verified affiliate sales','commissions.view':'View commission ledger','commissions.approve':'Approve/reverse commissions','payouts.manage':'Record commission payouts','audit.view':'Read audit history'}
DEFAULT_POLICY={'rates':{'Business':[1000,1500,2000],'Academy':[1500,2000,2500],'Studio':[800,1000,1200]},'founding_rates':{'Business':2000,'Academy':2500,'Studio':1200}}
KINDS=['General task','Academy session','Academy assessment','Business OS development','Release check','Studio delivery','Growth campaign','Customer support']
def owner(u):return u['email']==OWNER and u['role']=='admin'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
def uid():return secrets.token_hex(12)
def init(c):
 c.executescript('''
 CREATE TABLE IF NOT EXISTS affiliate_policy(id INTEGER PRIMARY KEY,value TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),permission TEXT NOT NULL,scope_type TEXT NOT NULL,scope_id TEXT NOT NULL,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS task_comments(id TEXT PRIMARY KEY,task_id TEXT REFERENCES tasks(id),author TEXT REFERENCES users(id),body TEXT NOT NULL,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,sender TEXT NOT NULL REFERENCES users(id),recipient TEXT NOT NULL REFERENCES users(id),body TEXT NOT NULL,created TEXT NOT NULL,read_at TEXT);
 CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),title TEXT NOT NULL,resource TEXT NOT NULL,record_id TEXT NOT NULL,created TEXT NOT NULL,read_at TEXT);
 CREATE TABLE IF NOT EXISTS meetings(id TEXT PRIMARY KEY,title TEXT NOT NULL,department TEXT NOT NULL,organizer TEXT REFERENCES users(id),starts TEXT NOT NULL,ends TEXT NOT NULL,url TEXT NOT NULL,status TEXT NOT NULL,notes TEXT NOT NULL,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS meeting_members(meeting_id TEXT REFERENCES meetings(id),user_id TEXT REFERENCES users(id),PRIMARY KEY(meeting_id,user_id));
 CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY,title TEXT NOT NULL,department TEXT NOT NULL,owner TEXT REFERENCES users(id),body TEXT NOT NULL,url TEXT NOT NULL,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS affiliates(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,program TEXT NOT NULL,owner TEXT REFERENCES users(id),status TEXT NOT NULL,training INTEGER NOT NULL DEFAULT 0,founding_number INTEGER UNIQUE,founding_until TEXT,code TEXT UNIQUE NOT NULL,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS affiliate_sales(id TEXT PRIMARY KEY,affiliate_id TEXT REFERENCES affiliates(id),invoice TEXT UNIQUE NOT NULL,customer TEXT NOT NULL,product TEXT NOT NULL,net_cents INTEGER NOT NULL,rate_bps INTEGER NOT NULL,commission_cents INTEGER NOT NULL,status TEXT NOT NULL,clear_on TEXT NOT NULL,evidence TEXT NOT NULL,payout_ref TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS subscription_commission_terms(affiliate_id TEXT REFERENCES affiliates(id),customer TEXT NOT NULL,rate_bps INTEGER NOT NULL,PRIMARY KEY(affiliate_id,customer));
 CREATE INDEX IF NOT EXISTS grants_user ON grants(user_id);
 CREATE INDEX IF NOT EXISTS message_inbox ON messages(recipient,read_at);
 CREATE INDEX IF NOT EXISTS notification_inbox ON notifications(user_id,read_at);
 ''')
 c.execute('INSERT OR IGNORE INTO affiliate_policy VALUES(1,?)',(json.dumps(DEFAULT_POLICY),))
 for table,column,typ in [('tasks','kind',"TEXT NOT NULL DEFAULT 'General task'"),('reviews','author','TEXT'),('reviews','reviewer','TEXT'),('affiliates','approved_on','TEXT'),('affiliate_sales','months','INTEGER NOT NULL DEFAULT 1')]:
  if column not in [x[1] for x in c.execute('PRAGMA table_info('+table+')')]:c.execute('ALTER TABLE '+table+' ADD COLUMN '+column+' '+typ)
def permissions(c,u):return [{'permission':p,'scope_type':'all','scope_id':''} for p in PERMISSIONS] if owner(u) else [dict(x) for x in c.execute('SELECT * FROM grants WHERE user_id=?',(u['id'],))]
def has(c,u,permission,department=None,record_id=None,assigned=None):
 if owner(u):return True
 for g in c.execute('SELECT * FROM grants WHERE user_id=? AND permission=?',(u['id'],permission)):
  if g['scope_type']=='all':return True
  if g['scope_type']=='department' and department and g['scope_id']==department:return True
  if g['scope_type']=='record' and record_id and g['scope_id']==record_id:return True
  if g['scope_type']=='assigned' and assigned==u['id']:return True
 return False
def any_permission(c,u,p):return owner(u) or bool(c.execute('SELECT 1 FROM grants WHERE user_id=? AND permission=?',(u['id'],p)).fetchone())
def audit(c,u,action,target):c.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',(u['id'],action,str(target),now()))
def notify(c,to,title,resource='',record=''):
 if to:c.execute('INSERT INTO notifications VALUES(?,?,?,?,?,?,NULL)',(uid(),to,title,resource,record,now()))
def row_permission(c,u,p,row):
 if not row:return False
 r=dict(row);return has(c,u,p,r.get('department'),r.get('id'),r.get('owner') or r.get('author'))
def can_message(c,u,target):return bool(target and target['active'] and (has(c,u,'messages.use',target['department'],target['id']) or (any_permission(c,u,'messages.use') and target['email']==OWNER)))
def meeting_allowed(c,u,m):
 member=c.execute('SELECT 1 FROM meeting_members WHERE meeting_id=? AND user_id=?',(m['id'],u['id'])).fetchone()
 return has(c,u,'meetings.view',m['department'],m['id'],u['id'] if member or m['organizer']==u['id'] else None)
def affiliate_allowed(c,u,p,a):return bool(a and has(c,u,p,'Growth',a['id'],a['owner']))
def notification_allowed(c,u,n):
 if not any_permission(c,u,'notifications.view'):return False
 resource=n['resource'];rid=n['record_id']
 if resource=='tasks':return row_permission(c,u,'tasks.view',c.execute('SELECT * FROM tasks WHERE id=?',(rid,)).fetchone())
 if resource=='reviews':return row_permission(c,u,'reviews.view',c.execute('SELECT * FROM reviews WHERE id=?',(rid,)).fetchone())
 if resource=='meetings':
  m=c.execute('SELECT * FROM meetings WHERE id=?',(rid,)).fetchone();return bool(m and meeting_allowed(c,u,m))
 if resource=='affiliates':return affiliate_allowed(c,u,'affiliates.view',c.execute('SELECT * FROM affiliates WHERE id=?',(rid,)).fetchone())
 if resource=='messages':
  m=c.execute('SELECT * FROM messages WHERE id=?',(rid,)).fetchone();return bool(m and can_message(c,u,c.execute('SELECT * FROM users WHERE id=?',(m['sender'],)).fetchone()))
 return not resource

def workspace(c,u,public):
 tasks=[dict(x) for x in c.execute('SELECT * FROM tasks ORDER BY created DESC') if row_permission(c,u,'tasks.view',x)]
 reviews=[dict(x) for x in c.execute('SELECT * FROM reviews ORDER BY created DESC') if row_permission(c,u,'reviews.view',x) or has(c,u,'reviews.view',x['department'],x['id'],x['reviewer'])]
 people=[public(x) for x in c.execute('SELECT * FROM users ORDER BY name') if x['id']==u['id'] or has(c,u,'people.view',x['department'],x['id'])]
 contacts=[{k:x[k] for k in ['id','name','department']} for x in c.execute('SELECT * FROM users WHERE active=1 AND id!=? ORDER BY name',(u['id'],)) if can_message(c,u,x)]
 message_rows=[dict(x) for x in c.execute('SELECT * FROM messages WHERE sender=? OR recipient=? ORDER BY created',(u['id'],u['id'])) if can_message(c,u,c.execute('SELECT * FROM users WHERE id=?',(x['recipient'] if x['sender']==u['id'] else x['sender'],)).fetchone())]
 notifications=[dict(x) for x in c.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY created DESC',(u['id'],)) if notification_allowed(c,u,x)]
 meetings=[dict(x) for x in c.execute('SELECT * FROM meetings ORDER BY starts') if meeting_allowed(c,u,x)]
 for m in meetings:m['participants']=[x[0] for x in c.execute('SELECT user_id FROM meeting_members WHERE meeting_id=?',(m['id'],))]
 affiliates=[dict(x) for x in c.execute('SELECT * FROM affiliates ORDER BY created DESC') if affiliate_allowed(c,u,'affiliates.view',x)]
 sales=[]
 for s in c.execute('SELECT * FROM affiliate_sales ORDER BY created DESC'):
  a=c.execute('SELECT * FROM affiliates WHERE id=?',(s['affiliate_id'],)).fetchone()
  if affiliate_allowed(c,u,'commissions.view',a):sales.append({**dict(s),'scope_owner':a['owner']})
 comments=[dict(x) for x in c.execute('SELECT * FROM task_comments ORDER BY created') if any(t['id']==x['task_id'] for t in tasks)]
 result={'user':public(u),'tasks':tasks,'reviews':reviews,'staff':people,'contacts':contacts,'messages':message_rows,'notifications':notifications,'meetings':meetings,'affiliates':affiliates,'sales':sales,'comments':comments,
 'announcements':[dict(x) for x in c.execute('SELECT * FROM announcements ORDER BY created DESC') if has(c,u,'announcements.view',x['department'],x['id']) or (x['department']=='All' and any_permission(c,u,'announcements.view'))],
 'resources':[dict(x) for x in c.execute('SELECT * FROM resources ORDER BY created DESC') if row_permission(c,u,'resources.view',x)],
 'audit':[dict(x) for x in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')] if has(c,u,'audit.view') else [],
 'invitations':[dict(x) for x in c.execute('SELECT token AS id,email,role,department,expires FROM invitations WHERE used=0 AND expires>?',(time.time(),))] if owner(u) else [],
 'grants':[dict(x) for x in c.execute('SELECT * FROM grants ORDER BY created')] if owner(u) else permissions(c,u),'permission_catalog':PERMISSIONS,'job_kinds':KINDS,
 'commission_policy':json.loads(c.execute('SELECT value FROM affiliate_policy WHERE id=1').fetchone()[0]),'google_meet_connected':__import__('integrations').google_connected()}
 result['unread_messages']=sum(x['recipient']==u['id'] and not x['read_at'] for x in message_rows);result['unread_notifications']=sum(not x['read_at'] for x in notifications)
 return result

def clean(b,key,maxlen=4000,required=True):
 value=str(b.get(key,'')).strip()
 if required and not value:raise ValueError('Enter '+key.replace('_',' ')+'.')
 if len(value)>maxlen:raise ValueError(key+' is too long.')
 return value

def google_meet():
 import integrations
 token=integrations.google_token() or os.environ.get('GOOGLE_MEET_ACCESS_TOKEN')
 if not token:
  if not all(os.environ.get(k) for k in ['GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REFRESH_TOKEN']):raise ValueError('Google Meet is not connected. Create a link in Google Meet and paste it into the meeting form.')
  payload=urllib.parse.urlencode({'client_id':os.environ['GOOGLE_CLIENT_ID'],'client_secret':os.environ['GOOGLE_CLIENT_SECRET'],'refresh_token':os.environ['GOOGLE_REFRESH_TOKEN'],'grant_type':'refresh_token'}).encode()
  try:
   with urllib.request.urlopen(urllib.request.Request('https://oauth2.googleapis.com/token',data=payload),timeout=15) as r:token=json.load(r)['access_token']
  except Exception:raise ValueError('Google authorization could not be refreshed. Ask the owner to reconnect it.')
 try:
  with urllib.request.urlopen(urllib.request.Request('https://meet.googleapis.com/v2/spaces',data=b'{}',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}),timeout=15) as r:url=json.load(r)['meetingUri']
 except Exception:raise ValueError('Google Meet creation failed. Check the user authorization and Meet API scope.')
 return url

def post(h,c,u,b):
 path=h.path.removeprefix('/api/')
 known=['programme-policy','permissions','tasks','task-edit','resource-update','task-status','task-comment','reviews','review-decision','announcements','messages','message-read','notification-read','meetings','meeting-status','resources','affiliates','affiliate-update','affiliate-qualify','affiliate-sales','commission-status','commission-payout']
 if path not in known:return False
 def deny(msg='This action has not been assigned to your account.'):
  h.send(403,{'error':msg});return True
 def ok(data=None):h.send(200,data or {'ok':True});return True
 dept=b.get('department',u['department'])
 if path=='programme-policy':
  if not owner(u):return deny('Only the owner can change programme commission rules.')
  policy=b.get('policy')
  if not isinstance(policy,dict) or set(policy)!=set(DEFAULT_POLICY):raise ValueError('Invalid commission policy.')
  for product in ['Business','Academy','Studio']:
   values=policy.get('rates',{}).get(product,[]);founding=policy.get('founding_rates',{}).get(product)
   if len(values)!=3 or any(not isinstance(v,int) or isinstance(v,bool) or v<0 or v>10000 for v in values+[founding]):raise ValueError('Rates must be between 0 and 100 percent.')
  c.execute('UPDATE affiliate_policy SET value=? WHERE id=1',(json.dumps(policy),));audit(c,u,'Changed programme commission policy',json.dumps(policy));return ok()
 if path=='permissions':
  if not owner(u):return deny('Only the HQ owner can assign access.')
  target=c.execute('SELECT * FROM users WHERE id=?',(b.get('user_id'),)).fetchone()
  if not target or owner(target):raise ValueError('Choose a staff account other than the owner.')
  grants=b.get('grants',[])
  if not isinstance(grants,list) or len(grants)>100:raise ValueError('Invalid permissions list.')
  for g in grants:
   if not isinstance(g,dict) or g.get('permission') not in PERMISSIONS or g.get('scope_type') not in ['assigned','department','record','all']:raise ValueError('Invalid permission or scope.')
   if g['scope_type']=='department' and g.get('scope_id') not in DEPTS:raise ValueError('Choose a valid department.')
   if g['scope_type']=='record' and not g.get('scope_id'):raise ValueError('Select a specific record ID.')
   if g['permission'] in ['tasks.create','reviews.submit','meetings.create','announcements.publish','resources.manage'] and g['scope_type'] in ['assigned','record']:raise ValueError('Creation permissions require a department or all scope.')
  c.execute('DELETE FROM grants WHERE user_id=?',(target['id'],))
  for g in grants:c.execute('INSERT INTO grants VALUES(?,?,?,?,?,?)',(uid(),target['id'],g['permission'],g['scope_type'],str(g.get('scope_id',''))[:100],now()))
  audit(c,u,'Updated granular permissions',target['email']);notify(c,target['id'],'Your access assignments were updated.');return ok()
 if path=='task-edit':
  t=c.execute('SELECT * FROM tasks WHERE id=?',(b.get('id'),)).fetchone()
  if not row_permission(c,u,'tasks.view',t) or not row_permission(c,u,'tasks.assign',t):return deny()
  assignee=b.get('owner') or None;title=clean(b,'title',160);due=clean(b,'due',20,False);kind=b.get('kind',t['kind']);priority=b.get('priority',t['priority'])
  if kind not in KINDS or priority not in ['Normal','High','Urgent']:raise ValueError('Invalid job type or priority.')
  if due:datetime.date.fromisoformat(due)
  if assignee and not c.execute('SELECT 1 FROM users WHERE id=? AND department=? AND active=1',(assignee,t['department'])).fetchone():raise ValueError('Choose active staff in the job department.')
  c.execute('UPDATE tasks SET title=?,description=?,owner=?,due=?,kind=?,priority=? WHERE id=?',(title,clean(b,'description',4000,False),assignee,due,kind,priority,t['id']))
  audit(c,u,'Updated job assignment',title);notify(c,assignee,'An assigned job was updated.','tasks',t['id']);return ok()
 if path=='resource-update':
  r=c.execute('SELECT * FROM resources WHERE id=?',(b.get('id'),)).fetchone()
  if not row_permission(c,u,'resources.view',r) or not (row_permission(c,u,'resources.update',r) or row_permission(c,u,'resources.manage',r)):return deny()
  url=clean(b,'url',1000,False)
  if url and urllib.parse.urlparse(url).scheme!='https':raise ValueError('Resource links must use HTTPS.')
  c.execute('UPDATE resources SET title=?,body=?,url=? WHERE id=?',(clean(b,'title',160),clean(b,'body'),url,r['id']));audit(c,u,'Edited knowledge resource',r['title']);return ok()
 if path=='tasks':
  if not has(c,u,'tasks.create',dept):return deny()
  title=clean(b,'title',160);assignee=b.get('owner') or None;kind=b.get('kind','General task');priority=b.get('priority','Normal');due=clean(b,'due',20,False)
  if dept not in DEPTS or kind not in KINDS or priority not in ['Normal','High','Urgent']:raise ValueError('Invalid job department, type or priority.')
  if due:datetime.date.fromisoformat(due)
  if assignee:
   person=c.execute('SELECT * FROM users WHERE id=? AND active=1',(assignee,)).fetchone()
   if not person or person['department']!=dept:raise ValueError('Assign an active user in the selected department.')
  tid=uid();c.execute('INSERT INTO tasks(id,title,description,department,owner,status,priority,due,created,kind) VALUES(?,?,?,?,?,?,?,?,?,?)',(tid,title,clean(b,'description',4000,False),dept,assignee,'To do',priority,due,now(),kind));audit(c,u,'Assigned job',title);notify(c,assignee,'A job has been assigned to you.','tasks',tid);return ok({'id':tid})
 if path in ['task-status','task-comment']:
  t=c.execute('SELECT * FROM tasks WHERE id=?',(b.get('id'),)).fetchone()
  if not row_permission(c,u,'tasks.view',t):return deny()
  if path=='task-comment':
   if not row_permission(c,u,'tasks.comment',t):return deny()
   c.execute('INSERT INTO task_comments VALUES(?,?,?,?,?)',(uid(),t['id'],u['id'],clean(b,'body'),now()));audit(c,u,'Commented on job',t['title']);
   if t['owner']!=u['id']:notify(c,t['owner'],'New discussion on your assigned job.','tasks',t['id'])
   return ok()
  status=b.get('status')
  if status not in ['To do','In progress','Review','Done']:raise ValueError('Invalid job status.')
  if status=='Done':
   if not row_permission(c,u,'tasks.approve',t):return deny('Completion requires an explicitly assigned approval permission.')
  elif not row_permission(c,u,'tasks.update',t):return deny()
  c.execute('UPDATE tasks SET status=? WHERE id=?',(status,t['id']));audit(c,u,'Job '+status,t['title']);return ok()
 if path=='reviews':
  if not has(c,u,'reviews.submit',dept):return deny()
  if dept not in DEPTS:raise ValueError('Invalid department.')
  reviewer=b.get('reviewer') or None
  if reviewer and not c.execute('SELECT 1 FROM users WHERE id=? AND active=1',(reviewer,)).fetchone():raise ValueError('Invalid reviewer.')
  rid=uid();title=clean(b,'title',160);c.execute('INSERT INTO reviews(id,title,department,description,status,feedback,created,author,reviewer) VALUES(?,?,?,?,?,?,?,?,?)',(rid,title,dept,clean(b,'description'),'Pending','',now(),u['id'],reviewer));audit(c,u,'Submitted review',title);notify(c,reviewer,'Work is waiting for your review.','reviews',rid);return ok({'id':rid})
 if path=='review-decision':
  r=c.execute('SELECT * FROM reviews WHERE id=?',(b.get('id'),)).fetchone()
  if not r or not has(c,u,'reviews.approve',r['department'],r['id'],r['reviewer']):return deny()
  status=b.get('status');feedback=clean(b,'feedback',4000,False)
  if status not in ['Approved','Changes requested'] or (status=='Changes requested' and not feedback):raise ValueError('Select a decision and include feedback for requested changes.')
  c.execute('UPDATE reviews SET status=?,feedback=? WHERE id=?',(status,feedback,r['id']));audit(c,u,'Review '+status,r['title']);notify(c,r['author'],'Your submitted review has a decision.','reviews',r['id']);return ok()
 if path=='announcements':
  if not has(c,u,'announcements.publish',dept):return deny()
  if dept not in DEPTS+['All']:raise ValueError('Invalid audience.')
  aid=uid();c.execute('INSERT INTO announcements VALUES(?,?,?,?,?)',(aid,clean(b,'title',160),clean(b,'body'),dept,now()));audit(c,u,'Published update',aid);return ok()
 if path=='messages':
  target=c.execute('SELECT * FROM users WHERE id=?',(b.get('recipient'),)).fetchone()
  if not can_message(c,u,target) or target['id']==u['id']:return deny('Messaging this recipient is outside your assigned access.')
  mid=uid();c.execute('INSERT INTO messages VALUES(?,?,?,?,?,NULL)',(mid,u['id'],target['id'],clean(b,'body'),now()));notify(c,target['id'],'You have a new private message.','messages',mid);return ok({'id':mid})
 if path=='message-read':
  target=c.execute('SELECT * FROM users WHERE id=?',(b.get('sender'),)).fetchone()
  if not can_message(c,u,target):return deny()
  c.execute('UPDATE messages SET read_at=? WHERE recipient=? AND sender=? AND read_at IS NULL',(now(),u['id'],target['id']));return ok()
 if path=='notification-read':
  if not any_permission(c,u,'notifications.view'):return deny()
  if b.get('all'):c.execute('UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL',(now(),u['id']))
  else:c.execute('UPDATE notifications SET read_at=? WHERE user_id=? AND id=?',(now(),u['id'],b.get('id')))
  return ok()
 if path=='meetings':
  if not has(c,u,'meetings.create',dept):return deny()
  title=clean(b,'title',160);start=clean(b,'starts',50);end=clean(b,'ends',50)
  try:sd=datetime.datetime.fromisoformat(start);ed=datetime.datetime.fromisoformat(end)
  except ValueError:raise ValueError('Enter valid meeting dates.')
  if not sd.tzinfo or not ed.tzinfo or ed<=sd:raise ValueError('Include a timezone and an end time after the start.')
  if dept not in DEPTS:raise ValueError('Invalid meeting department.')
  attendees=b.get('participants',[])
  if not isinstance(attendees,list) or len(attendees)>100:raise ValueError('Invalid participant list.')
  for person in attendees:
   target=c.execute('SELECT * FROM users WHERE id=? AND active=1',(person,)).fetchone()
   if not target or (not owner(u) and target['department']!=dept and target['email']!=OWNER):return deny('Participant is outside this meeting workspace.')
  url=clean(b,'url',500,False)
  if b.get('create_google'):url=google_meet()
  if not re.fullmatch(r'https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}',url):raise ValueError('Paste a valid Google Meet meeting link, such as https://meet.google.com/abc-defg-hij.')
  mid=uid();c.execute('INSERT INTO meetings VALUES(?,?,?,?,?,?,?,?,?,?)',(mid,title,dept,u['id'],start,end,url,'Scheduled',clean(b,'notes',4000,False),now()))
  for person in set(attendees+[u['id']]):c.execute('INSERT INTO meeting_members VALUES(?,?)',(mid,person));notify(c,person,'You have been invited to an HQ meeting.','meetings',mid)
  audit(c,u,'Scheduled meeting',title);return ok({'id':mid,'url':url})
 if path=='meeting-status':
  m=c.execute('SELECT * FROM meetings WHERE id=?',(b.get('id'),)).fetchone()
  if not m or not has(c,u,'meetings.manage',m['department'],m['id'],m['organizer']):return deny()
  if b.get('status') not in ['Scheduled','Completed','Cancelled']:raise ValueError('Invalid meeting status.')
  c.execute('UPDATE meetings SET status=? WHERE id=?',(b['status'],m['id']));audit(c,u,'Meeting '+b['status'],m['title']);return ok()
 if path=='resources':
  if not has(c,u,'resources.manage',dept):return deny()
  if dept not in DEPTS:raise ValueError('Invalid department.')
  url=clean(b,'url',1000,False)
  if url and urllib.parse.urlparse(url).scheme!='https':raise ValueError('Resource links must use HTTPS.')
  assigned=b.get('owner') or u['id']
  if not c.execute('SELECT 1 FROM users WHERE id=? AND active=1',(assigned,)).fetchone():raise ValueError('Invalid resource assignee.')
  rid=uid();c.execute('INSERT INTO resources VALUES(?,?,?,?,?,?,?)',(rid,clean(b,'title',160),dept,assigned,clean(b,'body'),url,now()));audit(c,u,'Created knowledge resource',rid);return ok({'id':rid})
 if path=='affiliates':
  if not has(c,u,'affiliates.manage','Growth',assigned=u['id']):return deny()
  program=b.get('program');email=clean(b,'email',254).lower();assigned=b.get('owner') or u['id']
  if program not in ['Referral','Sales','Creator','Campus','Agency'] or '@' not in email:raise ValueError('Select a programme and valid email.')
  if not c.execute('SELECT 1 FROM users WHERE id=? AND active=1',(assigned,)).fetchone():raise ValueError('Select an active staff owner.')
  if not owner(u) and assigned!=u['id']:return deny('You can register only your own partner records.')
  aid=uid();c.execute("INSERT INTO affiliates(id,name,email,program,owner,status,training,founding_number,founding_until,code,created) VALUES(?,?,?,?,?,'Applied',0,NULL,NULL,?,?)",(aid,clean(b,'name',100),email,program,assigned,'DB-'+secrets.token_hex(4).upper(),now()));audit(c,u,'Registered partner',email);notify(c,assigned,'A partner has been assigned to you.','affiliates',aid);return ok({'id':aid})
 if path in ['affiliate-update','affiliate-qualify','affiliate-sales']:
  a=c.execute('SELECT * FROM affiliates WHERE id=?',(b.get('id'),)).fetchone();permission={'affiliate-update':'affiliates.manage','affiliate-qualify':'affiliates.qualify','affiliate-sales':'sales.record'}[path]
  if not affiliate_allowed(c,u,permission,a):return deny()
  if path=='affiliate-update':
   status=b.get('status',a['status']);training=1 if b.get('training') else 0
   if status not in ['Applied','Onboarding','Active','Suspended']:raise ValueError('Invalid partner status.')
   c.execute('UPDATE affiliates SET status=?,training=?,approved_on=COALESCE(approved_on,?) WHERE id=?',(status,training,now() if status in ['Onboarding','Active'] else None,a['id']));audit(c,u,'Updated partner onboarding',a['email']);return ok()
  if path=='affiliate-qualify':
   if a['founding_number']:raise ValueError('Founding status is already confirmed.')
   if not a['training'] or a['status']!='Active':raise ValueError('Partner must finish training and be active.')
   sale=c.execute("SELECT * FROM affiliate_sales WHERE affiliate_id=? AND status IN ('Approved','Paid') AND clear_on<=? ORDER BY created LIMIT 1",(a['id'],datetime.date.today().isoformat())).fetchone()
   if not sale:raise ValueError('A verified, refund-cleared customer sale is required.')
   approved=datetime.datetime.fromisoformat(a['approved_on'] or a['created']);sold=datetime.datetime.fromisoformat(sale['created'])
   if sold>approved+datetime.timedelta(days=30):raise ValueError('The first qualifying sale must occur within 30 days of onboarding approval.')
   number=c.execute('SELECT COALESCE(MAX(founding_number),0)+1 FROM affiliates').fetchone()[0]
   if number>100:raise ValueError('All 100 confirmed founding places have been allocated.')
   expiry=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=365)).date().isoformat();c.execute('UPDATE affiliates SET founding_number=?,founding_until=? WHERE id=?',(number,expiry,a['id']));audit(c,u,'Confirmed Founding 100 place',str(number));return ok({'number':number})
  invoice=clean(b,'invoice',160);customer=clean(b,'customer',160);product=b.get('product');amount=b.get('net_cents');clear_on=clean(b,'clear_on',10);evidence=clean(b,'evidence',1000)
  if a['status']!='Active':raise ValueError('Activate this partner before recording sales.')
  if product not in ['Business','Academy','Studio'] or not isinstance(amount,int) or isinstance(amount,bool) or amount<=0 or amount>100000000:raise ValueError('Enter a valid product and eligible AED amount.')
  datetime.date.fromisoformat(clear_on)
  if not clean(b,'verified_by',100,False):raise ValueError('Record who verified the customer payment.')
  founding=a['founding_number'] and a['founding_until']>=datetime.date.today().isoformat()
  count=c.execute("SELECT COUNT(DISTINCT customer) FROM affiliate_sales WHERE affiliate_id=? AND status IN ('Approved','Paid') AND created>=?",(a['id'],(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=90)).isoformat())).fetchone()[0]
  level=2 if count>=15 else 1 if count>=5 else 0
  policy=json.loads(c.execute('SELECT value FROM affiliate_policy WHERE id=1').fetchone()[0]);rate=policy['founding_rates'][product] if founding else policy['rates'][product][level]
  months=b.get('months',1)
  if not isinstance(months,int) or isinstance(months,bool) or months<1 or months>12:raise ValueError('Subscription periods must cover between 1 and 12 paid months.')
  if product=='Business':
   used=c.execute("SELECT COALESCE(SUM(months),0) FROM affiliate_sales WHERE affiliate_id=? AND customer=? AND product='Business' AND status!='Reversed'",(a['id'],customer)).fetchone()[0]
   if used+months>12:raise ValueError('This customer has reached the first 12 paid subscription months.')
   term=c.execute('SELECT rate_bps FROM subscription_commission_terms WHERE affiliate_id=? AND customer=?',(a['id'],customer)).fetchone()
   if term:rate=term['rate_bps']
   else:c.execute('INSERT INTO subscription_commission_terms VALUES(?,?,?)',(a['id'],customer,rate))
  else:months=1
  commission=(amount*rate+5000)//10000;sid=uid();c.execute("INSERT INTO affiliate_sales(id,affiliate_id,invoice,customer,product,net_cents,rate_bps,commission_cents,status,clear_on,evidence,payout_ref,created,months) VALUES(?,?,?,?,?,?,?,?,?,?,?,'',?,?)",(sid,a['id'],invoice,customer,product,amount,rate,commission,'Pending',clear_on,evidence+' | Verified by: '+str(b['verified_by']),now(),months));audit(c,u,'Recorded verified affiliate sale',invoice);return ok({'id':sid,'rate_bps':rate,'commission_cents':commission})
 if path in ['commission-status','commission-payout']:
  sale=c.execute('SELECT * FROM affiliate_sales WHERE id=?',(b.get('id'),)).fetchone()
  a=c.execute('SELECT * FROM affiliates WHERE id=?',(sale['affiliate_id'],)).fetchone() if sale else None
  if not affiliate_allowed(c,u,'payouts.manage' if path=='commission-payout' else 'commissions.approve',a):return deny()
  if path=='commission-payout':
   if sale['status']!='Approved':raise ValueError('Only approved commission can be marked paid.')
   ref=clean(b,'payout_ref',160);c.execute("UPDATE affiliate_sales SET status='Paid',payout_ref=? WHERE id=?",(ref,sale['id']));audit(c,u,'Recorded commission payout',ref);return ok()
  status=b.get('status')
  if status not in ['Approved','Reversed']:raise ValueError('Invalid commission decision.')
  if status=='Approved' and (sale['status']!='Pending' or sale['clear_on']>datetime.date.today().isoformat()):raise ValueError('Commission must be pending and past its refund window.')
  if status=='Reversed' and sale['status']=='Paid':raise ValueError('Paid commission requires a documented recovery adjustment; it cannot be silently reversed.')
  if status=='Reversed' and not clean(b,'reason',1000,False):raise ValueError('Record the reversal reason.')
  c.execute('UPDATE affiliate_sales SET status=? WHERE id=?',(status,sale['id']));audit(c,u,'Commission '+status,sale['invoice']+': '+str(b.get('reason','')));return ok()
 return False
