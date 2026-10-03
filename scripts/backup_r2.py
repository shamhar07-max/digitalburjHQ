"""Encrypted PostgreSQL backups to Cloudflare R2 (S3 API), with retention and restore.

Usage:
  python scripts/backup_r2.py                 # dump, encrypt, upload, prune
  python scripts/backup_r2.py --list
  python scripts/backup_r2.py --restore KEY OUTFILE   # download + decrypt to a pg_restore-able file

The dump runs as the restricted application role (read access via its RLS policies),
so no administrative credential is needed. Dumps are Fernet-encrypted with HQ_BACKUP_KEY
before leaving the host. Standard library only; requests are AWS SigV4 signed.
"""
import argparse, datetime, hashlib, hmac, os, subprocess, sys, tempfile, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

REGION = 'auto'
SERVICE = 's3'
PREFIX = 'hq-backups/'


def _hmac(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sign(method, host, path, query, headers, payload_hash, access_key, secret_key, amz_date, region=REGION, service=SERVICE):
    """Return the Authorization header value for an AWS Signature Version 4 request."""
    date = amz_date[:8]
    headers = {k.lower(): str(v).strip() for k, v in headers.items()}
    headers['host'] = host
    headers['x-amz-date'] = amz_date
    headers['x-amz-content-sha256'] = payload_hash
    signed = ';'.join(sorted(headers))
    canonical_headers = ''.join(f'{k}:{headers[k]}\n' for k in sorted(headers))
    canonical_query = '&'.join(
        f'{urllib.parse.quote(k, safe="-_.~")}={urllib.parse.quote(v, safe="-_.~")}' for k, v in sorted(query.items()))
    canonical = '\n'.join([method, urllib.parse.quote(path, safe='/-_.~'), canonical_query, canonical_headers, signed, payload_hash])
    scope = f'{date}/{region}/{service}/aws4_request'
    to_sign = '\n'.join(['AWS4-HMAC-SHA256', amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(('AWS4' + secret_key).encode(), date), region), service), 'aws4_request')
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return f'AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={signature}'


class R2:
    def __init__(self):
        try:
            self.account = os.environ['R2_ACCOUNT_ID']
            self.bucket = os.environ['R2_BUCKET']
            self.access = os.environ['R2_ACCESS_KEY_ID']
            self.secret = os.environ['R2_SECRET_ACCESS_KEY']
        except KeyError as e:
            raise SystemExit(f'Missing environment variable {e.args[0]}')
        self.host = f'{self.account}.r2.cloudflarestorage.com'

    def request(self, method, key='', query=None, body=b''):
        query = query or {}
        path = '/' + self.bucket + ('/' + key if key else '')
        payload_hash = hashlib.sha256(body).hexdigest()
        amz_date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        auth = sign(method, self.host, path, query, {}, payload_hash, self.access, self.secret, amz_date)
        url = f'https://{self.host}{urllib.parse.quote(path, safe="/-_.~")}'
        if query:
            url += '?' + urllib.parse.urlencode(sorted(query.items()), quote_via=urllib.parse.quote, safe='-_.~')
        req = urllib.request.Request(url, data=body if method in ('PUT', 'POST') else None, method=method, headers={
            'x-amz-date': amz_date, 'x-amz-content-sha256': payload_hash, 'Authorization': auth})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise SystemExit(f'R2 {method} failed with HTTP {e.code}')

    def put(self, key, data):
        self.request('PUT', key, body=data)

    def get(self, key):
        return self.request('GET', key)

    def delete(self, key):
        self.request('DELETE', key)

    def list(self):
        items, token = [], None
        while True:
            q = {'list-type': '2', 'prefix': PREFIX}
            if token:
                q['continuation-token'] = token
            root = ET.fromstring(self.request('GET', '', q))
            ns = {'s': root.tag.split('}')[0].strip('{')}
            for c in root.findall('s:Contents', ns):
                items.append((c.find('s:Key', ns).text, c.find('s:LastModified', ns).text))
            if root.findtext('s:IsTruncated', namespaces=ns) != 'true':
                return sorted(items)
            token = root.findtext('s:NextContinuationToken', namespaces=ns)


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
        env = dict(os.environ, PGSSLMODE=os.environ.get('PGSSLMODE', 'verify-full' if os.environ.get('PGSSLROOTCERT') else 'require'))
        subprocess.run(['pg_dump', '--format=custom', f'--schema={schema}', '--no-owner', '--no-privileges', '--file', out, url],
                       check=True, env=env, stdout=subprocess.DEVNULL)
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
