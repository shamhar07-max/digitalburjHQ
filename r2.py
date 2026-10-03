"""Object storage: Cloudflare R2 over the S3 API (AWS SigV4, standard library only)
with a local-disk fallback for development and tests. Shared by the web app and backups."""
import datetime, hashlib, hmac, os, pathlib, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

REGION = 'auto'
SERVICE = 's3'


class StorageError(Exception):
    """Object storage rejected or could not complete a request."""


def _hmac(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signing_key(secret, date, region, service):
    return _hmac(_hmac(_hmac(_hmac(('AWS4' + secret).encode(), date), region), service), 'aws4_request')


def _quote(value):
    return urllib.parse.quote(str(value), safe='-_.~')


def _canonical_query(query):
    return '&'.join(f'{_quote(k)}={_quote(v)}' for k, v in sorted(query.items()))


def sign(method, host, path, query, headers, payload_hash, access_key, secret_key, amz_date, region=REGION, service=SERVICE):
    """Return the Authorization header value for an AWS Signature Version 4 request."""
    date = amz_date[:8]
    headers = {k.lower(): str(v).strip() for k, v in headers.items()}
    headers['host'] = host
    headers['x-amz-date'] = amz_date
    headers['x-amz-content-sha256'] = payload_hash
    signed = ';'.join(sorted(headers))
    canonical_headers = ''.join(f'{k}:{headers[k]}\n' for k in sorted(headers))
    canonical = '\n'.join([method, urllib.parse.quote(path, safe='/-_.~'), _canonical_query(query), canonical_headers, signed, payload_hash])
    scope = f'{date}/{region}/{service}/aws4_request'
    to_sign = '\n'.join(['AWS4-HMAC-SHA256', amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    signature = hmac.new(_signing_key(secret_key, date, region, service), to_sign.encode(), hashlib.sha256).hexdigest()
    return f'AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={signature}'


def presign(method, host, path, query, access_key, secret_key, amz_date, expires, region=REGION, service=SERVICE):
    """Return a query string that authorises one request for `expires` seconds (SigV4 query auth)."""
    date = amz_date[:8]
    scope = f'{date}/{region}/{service}/aws4_request'
    q = dict(query)
    q.update({'X-Amz-Algorithm': 'AWS4-HMAC-SHA256', 'X-Amz-Credential': f'{access_key}/{scope}', 'X-Amz-Date': amz_date,
              'X-Amz-Expires': str(expires), 'X-Amz-SignedHeaders': 'host'})
    canonical_query = _canonical_query(q)
    canonical = '\n'.join([method, urllib.parse.quote(path, safe='/-_.~'), canonical_query, f'host:{host}\n', 'host', 'UNSIGNED-PAYLOAD'])
    to_sign = '\n'.join(['AWS4-HMAC-SHA256', amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    signature = hmac.new(_signing_key(secret_key, date, region, service), to_sign.encode(), hashlib.sha256).hexdigest()
    return canonical_query + '&X-Amz-Signature=' + signature


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')


class R2:
    local = False

    def __init__(self, bucket, account, access, secret):
        self.bucket, self.access, self.secret = bucket, access, secret
        self.host = f'{account}.r2.cloudflarestorage.com'

    @classmethod
    def from_env(cls, bucket_var='R2_BUCKET'):
        try:
            return cls(os.environ[bucket_var], os.environ['R2_ACCOUNT_ID'], os.environ['R2_ACCESS_KEY_ID'], os.environ['R2_SECRET_ACCESS_KEY'])
        except KeyError as e:
            raise StorageError(f'Missing environment variable {e.args[0]}')

    def _path(self, key):
        return '/' + self.bucket + ('/' + key if key else '')

    def request(self, method, key='', query=None, body=b'', content_type=None):
        query = query or {}
        path = self._path(key)
        payload_hash = hashlib.sha256(body).hexdigest()
        amz_date = _now()
        extra = {'content-type': content_type} if content_type else {}
        auth = sign(method, self.host, path, query, extra, payload_hash, self.access, self.secret, amz_date)
        url = f'https://{self.host}{urllib.parse.quote(path, safe="/-_.~")}'
        if query:
            url += '?' + _canonical_query(query)
        headers = {'x-amz-date': amz_date, 'x-amz-content-sha256': payload_hash, 'Authorization': auth, **extra}
        req = urllib.request.Request(url, data=body if method in ('PUT', 'POST') else None, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise StorageError(f'R2 {method} failed with HTTP {e.code}')
        except urllib.error.URLError:
            raise StorageError(f'R2 {method} could not reach storage')

    def put(self, key, data, content_type='application/octet-stream'):
        self.request('PUT', key, body=data, content_type=content_type)

    def get(self, key):
        return self.request('GET', key)

    def delete(self, key):
        self.request('DELETE', key)

    def list(self, prefix=''):
        items, token = [], None
        while True:
            q = {'list-type': '2', 'prefix': prefix}
            if token:
                q['continuation-token'] = token
            root = ET.fromstring(self.request('GET', '', q))
            ns = {'s': root.tag.split('}')[0].strip('{')}
            for c in root.findall('s:Contents', ns):
                items.append((c.find('s:Key', ns).text, c.find('s:LastModified', ns).text))
            if root.findtext('s:IsTruncated', namespaces=ns) != 'true':
                return sorted(items)
            token = root.findtext('s:NextContinuationToken', namespaces=ns)

    def presigned_get(self, key, expires=60, filename=None, inline=False, content_type=None):
        query = {}
        if filename:
            ascii_name = filename.encode('ascii', 'ignore').decode().replace('"', '') or 'download'
            kind = 'inline' if inline else 'attachment'
            query['response-content-disposition'] = f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{_quote(filename)}"
        if content_type:
            query['response-content-type'] = content_type
        path = self._path(key)
        return f'https://{self.host}{urllib.parse.quote(path, safe="/-_.~")}?' + presign('GET', self.host, path, query, self.access, self.secret, _now(), expires)


class LocalStore:
    """Development/test storage on local disk. Never selected in production."""
    local = True

    def __init__(self, root):
        self.root = pathlib.Path(root)

    def _file(self, key):
        path = (self.root / key).resolve()
        path.relative_to(self.root.resolve())
        return path

    def put(self, key, data, content_type='application/octet-stream'):
        path = self._file(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key):
        try:
            return self._file(key).read_bytes()
        except FileNotFoundError:
            raise StorageError('Stored file is missing.')

    def delete(self, key):
        try:
            self._file(key).unlink()
        except FileNotFoundError:
            pass


def files_store():
    """Document storage selected by environment; production requires R2."""
    if all(os.environ.get(k) for k in ['R2_ACCOUNT_ID', 'R2_FILES_BUCKET', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY']):
        return R2.from_env('R2_FILES_BUCKET')
    if os.environ.get('HQ_ENV') == 'production':
        raise StorageError('Document storage is not configured. Ask the HQ owner to connect Cloudflare R2.')
    return LocalStore(os.environ.get('HQ_FILES_DIR', str(pathlib.Path(__file__).parent / 'private' / 'files')))
