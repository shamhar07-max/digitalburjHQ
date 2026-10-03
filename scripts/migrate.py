"""Apply versioned HQ schema and configure a restricted server database role."""
import argparse,json,os,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql
ROOT=pathlib.Path(__file__).resolve().parents[1]
def migrate(url,schema='hq',app_password=None):
 if not __import__('re').fullmatch(r'[a-z][a-z0-9_]{0,62}',schema):raise ValueError('Invalid schema')
 with psycopg.connect(url,prepare_threshold=None) as c:
  c.execute('SELECT pg_advisory_xact_lock(72844001)')
  script=(ROOT/'sql/schema.sql').read_text().replace(' hq',' '+schema).replace('TO hq','TO '+schema)
  c.execute(script,prepare=False)
  # Supabase public API roles get neither schema nor table privileges.
  for name in ['anon','authenticated','service_role']:
   if c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(name,)).fetchone():c.execute(sql.SQL('REVOKE ALL ON SCHEMA {} FROM {}').format(sql.Identifier(schema),sql.Identifier(name)))
  if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='digitalburj_app'").fetchone():c.execute('CREATE ROLE digitalburj_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS')
  c.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO digitalburj_app').format(sql.Identifier(schema)))
  c.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO digitalburj_app').format(sql.Identifier(schema)))
  c.execute(sql.SQL('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO digitalburj_app').format(sql.Identifier(schema)))
  for table in json.loads((ROOT/'sql/tables.json').read_text()):
   target=sql.Identifier(schema,table)
   c.execute(sql.SQL('DROP POLICY IF EXISTS hq_server ON {}').format(target))
   c.execute(sql.SQL('CREATE POLICY hq_server ON {} TO digitalburj_app USING (true) WITH CHECK (true)').format(target))
  if app_password:
   if len(app_password)<24:raise ValueError('Application database password must contain at least 24 characters.')
   c.execute(sql.SQL('ALTER ROLE digitalburj_app LOGIN PASSWORD {}').format(sql.Literal(app_password)))
  c.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
  assert c.execute('SELECT version FROM schema_version WHERE id=1').fetchone()[0]==1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--create-app-login',action='store_true');a=p.parse_args()
 url=os.environ.get('MIGRATION_DATABASE_URL')
 if not url:raise SystemExit('Set MIGRATION_DATABASE_URL privately.')
 if a.create_app_login and not os.environ.get('HQ_APP_DB_PASSWORD'):raise SystemExit('Set HQ_APP_DB_PASSWORD privately.')
 migrate(url,os.environ.get('HQ_DB_SCHEMA','hq'),os.environ.get('HQ_APP_DB_PASSWORD') if a.create_app_login else None)
 print('HQ schema and restricted database role verified.')
