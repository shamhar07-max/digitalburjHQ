"""Import existing HQ business data into an empty migrated PostgreSQL database."""
import argparse,os,pathlib,sqlite3,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import database
SKIP={'invitations','sessions','partner_sessions','oauth_states','attempts','account_tokens','mail_outbox','service_tokens','schema_version'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('sqlite_file');a=p.parse_args()
 if not os.environ.get('DATABASE_URL'):raise SystemExit('Set the target DATABASE_URL privately.')
 source=sqlite3.connect('file:'+str(pathlib.Path(a.sqlite_file).resolve())+'?mode=ro',uri=True);source.row_factory=sqlite3.Row
 with database.connection(a.sqlite_file) as c:
  database.verify(c)
  if c.execute('SELECT 1 FROM users LIMIT 1').fetchone():raise SystemExit('Target already has staff data. Import aborted.')
  tables=source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid").fetchall()
  counts={}
  for t in tables:
   name=t['name']
   if name in SKIP:continue
   # Table/column identifiers come only from the trusted local HQ schema.
   if not __import__('re').fullmatch('[a-z_]+',name):raise ValueError('Invalid source table')
   rows=source.execute('SELECT * FROM '+name).fetchall();counts[name]=len(rows)
   if name=='affiliate_policy':
    for r in rows:c.execute('UPDATE affiliate_policy SET value=? WHERE id=?',(r['value'],r['id']))
    continue
   for r in rows:
    columns=list(r.keys());c.execute('INSERT INTO '+name+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(r))
  c.execute("SELECT setval(pg_get_serial_sequence('audit','id'),COALESCE(MAX(id),1),MAX(id) IS NOT NULL) FROM audit")
 print('Import committed. Existing sessions and external tokens were not transferred. Record counts:',counts)
