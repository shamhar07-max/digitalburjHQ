import datetime, hashlib, importlib.util, os, pathlib, unittest
spec = importlib.util.spec_from_file_location('backup_r2', pathlib.Path(__file__).parent / 'scripts' / 'backup_r2.py')
backup_r2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(backup_r2)

import r2


class FakeR2:
    def __init__(self, items): self.items = items; self.deleted = []
    def list(self): return self.items
    def delete(self, key): self.deleted.append(key)

class BackupTests(unittest.TestCase):
    def test_sigv4_matches_aws_published_example(self):
        # GET Object example from the AWS Signature Version 4 documentation.
        auth = backup_r2.sign('GET', 'examplebucket.s3.amazonaws.com', '/test.txt', {}, {'Range': 'bytes=0-9'},
            hashlib.sha256(b'').hexdigest(), 'AKIAIOSFODNN7EXAMPLE', 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
            '20130524T000000Z', region='us-east-1')
        self.assertTrue(auth.endswith('Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41'))

    def test_presigned_url_matches_aws_published_example(self):
        # Presigned GET example from the AWS Signature Version 4 query-string documentation.
        q = r2.presign('GET', 'examplebucket.s3.amazonaws.com', '/test.txt', {}, 'AKIAIOSFODNN7EXAMPLE',
            'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY', '20130524T000000Z', 86400, region='us-east-1')
        self.assertTrue(q.endswith('X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404'))

    def test_local_store_round_trip_and_traversal_guard(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            store = r2.LocalStore(d)
            store.put('a/b.txt', b'hello')
            self.assertEqual(store.get('a/b.txt'), b'hello')
            store.delete('a/b.txt')
            with self.assertRaises(r2.StorageError):
                store.get('a/b.txt')
            with self.assertRaises(ValueError):
                store.put('../escape.txt', b'x')

    def test_prune_deletes_old_but_keeps_newest(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        def item(days):
            when = now - datetime.timedelta(days=days)
            return (f'hq-backups/hq-{when:%Y%m%dT%H%M%SZ}.dump.enc', when.isoformat())
        items = sorted([item(90), item(60), item(40), item(2), item(1)])
        r2 = FakeR2(items)
        backup_r2.prune(r2, keep_days=30, keep_min=1)
        self.assertEqual(sorted(r2.deleted), sorted(k for k, _ in items[:3]))

    def test_prune_never_empties_the_bucket(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        old = sorted((f'hq-backups/hq-{(now - datetime.timedelta(days=100 + i)):%Y%m%dT%H%M%SZ}.dump.enc', (now - datetime.timedelta(days=100 + i)).isoformat()) for i in range(3))
        r2 = FakeR2(old); backup_r2.prune(r2, keep_days=30, keep_min=2)
        self.assertEqual(len(r2.deleted), 1)

if __name__ == '__main__': unittest.main()
