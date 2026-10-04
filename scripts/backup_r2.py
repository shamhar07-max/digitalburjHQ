"""Encrypted PostgreSQL backups to Cloudflare R2 (S3 API), with retention and restore.

Usage:
  python scripts/backup_r2.py                 # dump, encrypt, upload, prune
  python scripts/backup_r2.py --list
  python scripts/backup_r2.py --restore KEY OUTFILE   # download + decrypt to a pg_restore-able file

The dump runs as the restricted application role (read access via its RLS policies),
so no administrative credential is needed. Dumps are Fernet-encrypted with HQ_BACKUP_KEY
before leaving the host. Standard library only; requests are AWS SigV4 signed.
"""
import argparse, urllib.parse, datetime, os, pathlib, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from r2 import R2 as _R2, StorageError, sign  # noqa: F401  (sign re-exported for tests)

PREFIX = 'hq-backups/'


class _Bucket:
    """Backup view of the bucket: fixed prefix, storage errors become process exits."""

    def __init__(self):
        try:
            self.r2 = _R2.from_env('R2_BUCKET')
        except StorageError as e:
            raise SystemExit(str(e))

    def _call(self, name, *args):
        try:
            return getattr(self.r2, name)(*args)
        except StorageError as e:
            raise SystemExit(str(e))

    def put(self, key, data):
        self._call('put', key, data)

    def get(self, key):
        return self._call('get', key)

    def delete(self, key):
        self._call('delete', key)

    def list(self):
        return self._call('list', PREFIX)


def R2():
    return _Bucket()


def fernet():
    from cryptography.fernet import Fernet
    key = os.environ.get('HQ_BACKUP_KEY')
    if not key:
        raise SystemExit('Missing environment variable HQ_BACKUP_KEY')
    return Fernet(key.encode())


def dump():
    url = os.environ.get('BACKUP_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not url:
        raise SystemExit('Missing environment variable DATABASE_URL')
    schema = os.environ.get('HQ_DB_SCHEMA', 'hq')
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'hq.dump')
        u = urllib.parse.urlparse(url)
        # Connection details travel in PG* variables, never on the command line, so a failure can't echo the password.
        env = dict(os.environ, PGHOST=u.hostname or '', PGPORT=str(u.port or 5432), PGUSER=urllib.parse.unquote(u.username or ''),
                   PGPASSWORD=urllib.parse.unquote(u.password or ''), PGDATABASE=(u.path or '/postgres').lstrip('/') or 'postgres',
                   PGSSLMODE=os.environ.get('PGSSLMODE', 'verify-full' if os.environ.get('PGSSLROOTCERT') else 'require'))
        try:
            # RLS is enforced for the app role (policy: all rows), so pg_dump must be told to read through it.
            subprocess.run(['pg_dump', '--format=custom', '--enable-row-security', f'--schema={schema}', '--no-owner', '--no-privileges',
                            '--file', out], check=True, env=env, stdout=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            raise SystemExit(f'pg_dump failed with exit status {e.returncode}')
        with open(out, 'rb') as f:
            return f.read()


def backup(r2, keep_days, keep_min):
    data = dump()
    if len(data) < 1024:
        raise SystemExit('Dump is suspiciously small; refusing to upload.')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    key = f'{PREFIX}hq-{stamp}.dump.enc'
    r2.put(key, fernet().encrypt(data))
    # Read back and verify before pruning anything.
    if fernet().decrypt(r2.get(key)) != data:
        raise SystemExit('Upload verification failed.')
    print(f'Uploaded and verified {key} ({len(data)} bytes before encryption)')
    prune(r2, keep_days, keep_min)


def prune(r2, keep_days, keep_min):
    items = r2.list()
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=keep_days)
    old = [k for k, modified in items if datetime.datetime.fromisoformat(modified.replace('Z', '+00:00')) < cutoff]
    # Always keep the newest keep_min backups regardless of age.
    protected = {k for k, _ in items[-keep_min:]}
    for key in old:
        if key not in protected:
            r2.delete(key)
            print('Pruned', key)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--list', action='store_true')
    p.add_argument('--restore', nargs=2, metavar=('KEY', 'OUTFILE'))
    a = p.parse_args()
    r2 = R2()
    if a.list:
        for key, modified in r2.list():
            print(modified, key)
    elif a.restore:
        key, out = a.restore
        with open(out, 'wb') as f:
            f.write(fernet().decrypt(r2.get(key)))
        print(f'Decrypted to {out}. Restore into a SEPARATE test database with pg_restore --no-owner.')
    else:
        backup(r2, int(os.environ.get('HQ_BACKUP_RETENTION_DAYS', '30')), int(os.environ.get('HQ_BACKUP_KEEP_MIN', '7')))


if __name__ == '__main__':
    sys.exit(main())
