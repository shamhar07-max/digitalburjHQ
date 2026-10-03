"""SQLite development and pooled private-schema PostgreSQL persistence."""
import contextlib, hashlib, os, pathlib, re, sqlite3, threading
try:
 import psycopg
 from psycopg_pool import ConnectionPool
except ImportError:
 psycopg=None
POOLS={};LOCK=threading.Lock()
class Row(dict):
 def __getitem__(self,key):return list(self.values())[key] if isinstance(key,int) else super().__getitem__(key)
def row_factory(cursor):
 names=[column.name for column in (cursor.description or [])]
 return lambda values:Row(zip(names,values))
class SQLiteConnection(sqlite3.Connection):
 is_postgres=False
 def __exit__(self,*args):
  try:return super().__exit__(*args)
  finally:self.close()
class DirectConnections:
 def __init__(self,url,kwargs):self.url=url;self.kwargs=kwargs
 def getconn(self):return psycopg.connect(self.url,**self.kwargs)
 def putconn(self,c):c.close()

class PostgresConnection:
 is_postgres=True
 def __init__(self,pool,schema):
  self.pool=pool;self.raw=pool.getconn();self.schema=schema
  try:
   self.setup()
  except Exception:
   self.raw.close();self.pool.putconn(self.raw);self.raw=None;raise
 def setup(self):
  # One round trip: transaction-local settings equivalent to SET LOCAL search_path / statement_timeout / lock_timeout.
  self.raw.execute("SELECT set_config('search_path',%s,true),set_config('statement_timeout','15000ms',true),set_config('lock_timeout','10000ms',true)",(self.schema,))
 def __enter__(self):return self
 def __exit__(self,typ,value,tb):
  try:
   if typ:
    try:self.raw.rollback()
    except Exception:self.raw.close()
   else:self.raw.commit()
  finally:self.close()
 def close(self):
  if self.raw is not None:
   self.pool.putconn(self.raw);self.raw=None
 def commit(self):
  self.raw.commit();self.setup()
 def rollback(self):
  self.raw.rollback();self.setup()
 def execute(self,query,params=()):
  if query.startswith('PRAGMA table_info('):
   table=query.split('(',1)[1].split(')',1)[0]
   return self.raw.execute('SELECT ordinal_position-1 AS cid,column_name AS name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position',(self.schema,table))
  if query.startswith('INSERT OR IGNORE '):query=query.replace('INSERT OR IGNORE ','INSERT ',1)+' ON CONFLICT DO NOTHING'
  if query.startswith('INSERT OR REPLACE INTO attempts '):query=query.replace('INSERT OR REPLACE ','INSERT ',1)+' ON CONFLICT(key) DO UPDATE SET count=excluded.count,until=excluded.until'
  if 'INSERT OR REPLACE ' in query:raise ValueError('Unsupported replacement SQL; use an explicit upsert.')
  # Queries are fixed application SQL; placeholders never interpolate request data.
  query=query.replace('?', '%s')
  return self.raw.execute(query,params)
 def executescript(self,script):
  for statement in script.split(';'):
   if statement.strip():self.raw.execute(statement)
 def __getattr__(self,key):return getattr(self.raw,key)

def schema_for(path=None):
 schema=os.environ.get('HQ_DB_SCHEMA','hq')
 if os.environ.get('HQ_TEST_POSTGRES')=='1':schema='test_'+hashlib.sha256(str(path).encode()).hexdigest()[:16]
 if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}',schema):raise RuntimeError('Invalid private database schema.')
 return schema

def connection(path):
 url=os.environ.get('DATABASE_URL')
 if not url:
  if os.environ.get('HQ_ENV')=='production':raise RuntimeError('Production requires DATABASE_URL; SQLite fallback is disabled.')
  c=sqlite3.connect(path,timeout=15,factory=SQLiteConnection);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL');return c
 if psycopg is None:raise RuntimeError('Install the pinned PostgreSQL dependencies.')
 schema=schema_for(path);key=(url,schema)
 with LOCK:
  if key not in POOLS:
   kwargs={'row_factory':row_factory,'prepare_threshold':None,'connect_timeout':10}
   if os.environ.get('HQ_ENV')=='production':kwargs['sslmode']='verify-full'
   size=int(os.environ.get('HQ_DB_POOL_SIZE','8'))
   POOLS[key]=ConnectionPool(url,min_size=0,max_size=size,timeout=10,kwargs=kwargs,open=True) if size else DirectConnections(url,kwargs)
 return PostgresConnection(POOLS[key],schema)

def integrity_error(e):return isinstance(e,sqlite3.IntegrityError) or bool(psycopg and isinstance(e,psycopg.IntegrityError))

def verify(c):
 if c.is_postgres:
  if os.environ.get('HQ_ENV')=='production' and c.execute('SELECT current_user').fetchone()[0]!='digitalburj_app':raise RuntimeError('Production requires the restricted application database role.')
  r=c.execute('SELECT version FROM schema_version WHERE id=1').fetchone()
  if not r or r['version']!=1:raise RuntimeError('Apply the HQ PostgreSQL schema before startup.')
