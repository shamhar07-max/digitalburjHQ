"""Opt-in isolated PostgreSQL test schemas; never run against production."""
import os

def prepare(server):
 if not os.environ.get('DATABASE_URL'):return
 if os.environ.get('HQ_TEST_POSTGRES')!='1' or os.environ.get('HQ_ENV')=='production':raise RuntimeError('PostgreSQL tests require an explicit disposable test database.')
 from scripts.migrate import migrate
 import database
 migrate(os.environ['DATABASE_URL'],database.schema_for(server.DB))
