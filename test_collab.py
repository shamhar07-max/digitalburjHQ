import http.cookiejar, json, os, pathlib, socket, subprocess, tempfile, time, unittest, urllib.error, urllib.parse, urllib.request
import server
import test_support

PDF = b'%PDF-1.4\n%test document\n' + b'0' * 64
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 64


class CollabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        server.DB = pathlib.Path(cls.tmp.name) / 'test.sqlite3'
        server.BOOTSTRAP = pathlib.Path(cls.tmp.name) / 'disabled.json'
        test_support.prepare(server)
        server.init()
        grants = {
            'teacher': [('messages.use', 'department', 'Academy'), ('notifications.view', 'assigned', ''), ('files.personal', 'assigned', ''), ('files.view', 'department', 'Academy')],
            'teacher2': [('messages.use', 'department', 'Academy'), ('notifications.view', 'assigned', ''), ('files.personal', 'assigned', ''), ('files.view', 'department', 'Academy'), ('files.upload', 'department', 'Academy')],
            'dev': [('messages.use', 'department', 'Business OS'), ('files.personal', 'assigned', ''), ('files.view', 'department', 'Business OS')],
            'nochat': [('tasks.view', 'assigned', '')]}
        with server.connection() as c:
            for uid, email, role, dept in [('admin', 'shamhar07@gmail.com', 'admin', 'Business OS'), ('teacher', 'teacher@test.invalid', 'teacher', 'Academy'),
                                           ('teacher2', 'teacher2@test.invalid', 'teacher', 'Academy'), ('dev', 'dev@test.invalid', 'developer', 'Business OS'), ('nochat', 'nochat@test.invalid', 'designer', 'Studio')]:
                c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)', (uid, uid, email, server.pw_hash('testing-password-123'), role, dept))
            for uid, rows in grants.items():
                for permission, scope, scope_id in rows:
                    c.execute('INSERT INTO grants VALUES(?,?,?,?,?,?)', (os.urandom(6).hex(), uid, permission, scope, scope_id, '2026-01-01'))
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); cls.port = sock.getsockname()[1]; sock.close()
        cls.base = f'http://127.0.0.1:{cls.port}'
        env = {**os.environ, 'HQ_DB': str(server.DB), 'HQ_BOOTSTRAP': str(server.BOOTSTRAP), 'HQ_FILES_DIR': cls.tmp.name + '/files', 'HQ_MAX_UPLOAD_MB': '1'}
        cls.proc = subprocess.Popen(['python3', 'server.py', '--port', str(cls.port)], env=env, stdout=subprocess.DEVNULL)
        for _ in range(50):
            try:
                urllib.request.urlopen(cls.base); break
            except Exception:
                time.sleep(.1)
        cls.sessions = {}

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate(); cls.proc.wait(); cls.tmp.cleanup()

    def login(self, uid):
        if uid not in self.sessions:
            email = 'shamhar07@gmail.com' if uid == 'admin' else uid + '@test.invalid'
            op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            status, data = self.call(op, 'login', {'email': email, 'password': 'testing-password-123'})
            self.assertEqual(status, 200)
            self.sessions[uid] = (op, data['csrf'])
        return self.sessions[uid]

    def call(self, op, path, data=None, csrf=''):
        req = urllib.request.Request(self.base + '/api/' + path, data=json.dumps(data).encode() if data is not None else None, headers={'Content-Type': 'application/json', 'X-CSRF-Token': csrf})
        try:
            r = op.open(req)
        except urllib.error.HTTPError as e:
            r = e
        return r.code, json.loads(r.read())

    def api(self, uid, path, data=None):
        op, csrf = self.login(uid)
        return self.call(op, path, data, csrf)

    def upload(self, uid, params, body, name=None):
        op, csrf = self.login(uid)
        q = urllib.parse.urlencode({**params, 'name': name or params.get('name', 'doc.pdf')})
        req = urllib.request.Request(self.base + '/api/files/upload?' + q, data=body, method='POST', headers={'Content-Type': 'application/octet-stream', 'X-CSRF-Token': csrf})
        try:
            r = op.open(req)
        except urllib.error.HTTPError as e:
            r = e
        return r.code, json.loads(r.read())

    def raw_get(self, uid, path):
        op, _ = self.login(uid)
        try:
            r = op.open(self.base + '/api/' + path)
        except urllib.error.HTTPError as e:
            r = e
        return r.code, r.read(), r.headers

    def send(self, uid, channel, body, **extra):
        return self.api(uid, 'chat/send', {'channel': channel, 'body': body, **extra})

    # ------------------------------------------------------------ chat
    def test_chat_access_flow_and_privacy(self):
        self.assertEqual(self.api('nochat', 'chat/send', {'channel': 'company', 'body': 'x'})[0], 403)
        self.assertEqual(self.call(self.login('nochat')[0], 'chat/bootstrap')[0], 403)
        _, boot = self.call(self.login('teacher')[0], 'chat/bootstrap')
        ids = {c['id'] for c in boot['channels']}
        self.assertIn('company', ids); self.assertIn('dept:Academy', ids); self.assertNotIn('dept:Studio', ids); self.assertNotIn('dept:Business OS', ids)
        self.assertIn('admin', {p['id'] for p in boot['people']}); self.assertNotIn('dev', {p['id'] for p in boot['people']})
        status, dm = self.api('teacher', 'chat/dm', {'user_id': 'admin'}); self.assertEqual(status, 200)
        cid = dm['channel']
        status, sent = self.send('teacher', cid, 'Hello, the rubric is ready.'); self.assertEqual(status, 200)
        # an unrelated staff member can neither open nor post into the conversation
        self.assertEqual(self.api('dev', 'chat/dm', {'user_id': 'teacher'})[0], 403)
        self.assertEqual(self.send('dev', cid, 'intrude')[0], 403)
        op, _ = self.login('dev')
        self.assertEqual(self.call(op, 'chat/messages?channel=' + urllib.parse.quote(cid))[0], 403)
        # the recipient sees it unread, then reads it
        _, boot = self.call(self.login('admin')[0], 'chat/bootstrap')
        entry = next(c for c in boot['channels'] if c['id'] == cid)
        self.assertEqual(entry['unread'], 1); self.assertEqual(entry['name'], 'teacher'); self.assertEqual(entry['last']['body'], 'Hello, the rubric is ready.')
        self.assertEqual(self.api('admin', 'chat/read', {'channel': cid})[0], 200)
        _, sync = self.call(self.login('teacher')[0], 'chat/sync?cursor=' + urllib.parse.quote(boot['cursor']))
        self.assertTrue(next(c for c in sync['channels'] if c['id'] == cid)['peer_read'] >= sent['created'])
        _, hist = self.call(self.login('admin')[0], 'chat/messages?channel=' + urllib.parse.quote(cid))
        self.assertEqual([m['body'] for m in hist['messages']], ['Hello, the rubric is ready.'])

    def test_message_lifecycle_reactions_replies_pins_mentions(self):
        _, a = self.send('teacher', 'dept:Academy', 'Plan for Friday @teacher2 please check'); mid = a['id']
        self.assertEqual(self.send('dev', 'dept:Academy', 'outsider')[0], 403)
        self.assertEqual(self.api('teacher2', 'chat/edit', {'id': mid, 'body': 'hijack'})[0], 403)
        self.assertEqual(self.api('teacher', 'chat/edit', {'id': mid, 'body': 'Plan for Friday @teacher2 (edited)'})[0], 200)
        self.assertEqual(self.api('teacher2', 'chat/react', {'id': mid, 'emoji': '👍'})[0], 200)
        self.assertEqual(self.api('teacher2', 'chat/react', {'id': mid, 'emoji': '🧨'})[0], 400)
        status, r = self.send('teacher2', 'dept:Academy', 'On it', reply_to=mid); self.assertEqual(status, 200)
        self.assertEqual(self.send('teacher2', 'dept:Academy', 'bad', reply_to='nope')[0], 400)
        _, hist = self.call(self.login('teacher')[0], 'chat/messages?channel=dept%3AAcademy')
        first = next(m for m in hist['messages'] if m['id'] == mid); reply = next(m for m in hist['messages'] if m['id'] == r['id'])
        self.assertEqual(first['reactions'], {'👍': ['teacher2']}); self.assertEqual(first['edited'], 1); self.assertEqual(reply['reply']['id'], mid)
        self.assertEqual(self.api('teacher2', 'chat/react', {'id': mid, 'emoji': '👍'})[0], 200)
        _, hist = self.call(self.login('teacher')[0], 'chat/messages?channel=dept%3AAcademy')
        self.assertEqual(next(m for m in hist['messages'] if m['id'] == mid)['reactions'], {})
        # mention notified; non-members are not
        _, ws = self.call(self.login('teacher2')[0], 'workspace')
        self.assertTrue(any('mentioned you' in n['title'] for n in ws['notifications']))
        # pinning shared-channel messages is a moderator action
        self.assertEqual(self.api('teacher', 'chat/pin', {'id': mid})[0], 403)
        self.assertEqual(self.api('admin', 'chat/pin', {'id': mid})[0], 200)
        # delete leaves a tombstone and clears content; others cannot delete, moderators can
        self.assertEqual(self.api('teacher2', 'chat/delete', {'id': mid})[0], 403)
        self.assertEqual(self.api('admin', 'chat/delete', {'id': mid})[0], 200)
        _, hist = self.call(self.login('teacher')[0], 'chat/messages?channel=dept%3AAcademy')
        gone = next(m for m in hist['messages'] if m['id'] == mid); self.assertEqual((gone['deleted'], gone['body']), (1, ''))
        self.assertEqual(self.api('teacher', 'chat/edit', {'id': mid, 'body': 'revive'})[0], 403)

    def test_sync_returns_changes_after_cursor(self):
        _, boot = self.call(self.login('teacher2')[0], 'chat/bootstrap')
        self.send('teacher', 'company', 'Company-wide note')
        _, sync = self.call(self.login('teacher2')[0], 'chat/sync?cursor=' + urllib.parse.quote(boot['cursor']) + '&typing=company')
        self.assertIn('Company-wide note', [m['body'] for m in sync['messages']])
        self.assertGreaterEqual(sync['total_unread'], 1)
        _, other = self.call(self.login('teacher')[0], 'chat/sync?cursor=' + urllib.parse.quote(boot['cursor']))
        self.assertEqual(other['typing'].get('company'), ['teacher2']); self.assertIn('teacher2', other['online'])
        _, devsync = self.call(self.login('dev')[0], 'chat/sync?cursor=' + urllib.parse.quote(boot['cursor']))
        self.assertNotIn('dept:Academy', [c['id'] for c in devsync['channels']])

    def test_group_channels_are_member_only(self):
        status, g = self.api('teacher', 'chat/group', {'name': 'Rubric review', 'members': ['teacher2']}); self.assertEqual(status, 200)
        self.assertEqual(self.api('teacher', 'chat/group', {'name': 'Leak', 'members': ['dev']})[0], 403)
        self.assertEqual(self.send('teacher2', g['channel'], 'in')[0], 200)
        self.assertEqual(self.send('admin', g['channel'], 'owner is not a member')[0], 403)

    # ------------------------------------------------------------ files
    def test_personal_vault_is_private_even_from_the_owner(self):
        status, meta = self.upload('teacher', {'scope': 'personal'}, PDF, 'Contract draft.pdf'); self.assertEqual(status, 201)
        self.assertEqual(meta['mime'], 'application/pdf'); self.assertEqual(meta['size'], len(PDF))
        code, body, headers = self.raw_get('teacher', 'files/download?id=' + meta['id']); self.assertEqual((code, body), (200, PDF))
        self.assertIn('attachment', headers['Content-Disposition']); self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.raw_get('admin', 'files/download?id=' + meta['id'])[0], 403)
        self.assertEqual(self.raw_get('dev', 'files/download?id=' + meta['id'])[0], 403)
        _, listing = self.call(self.login('admin')[0], 'files?scope=personal'); self.assertNotIn(meta['id'], [x['id'] for x in listing['files']])
        # share, read-only access, then unshare
        self.assertEqual(self.api('teacher', 'files/share', {'id': meta['id'], 'user_ids': ['admin']})[0], 200)
        self.assertEqual(self.raw_get('admin', 'files/download?id=' + meta['id'])[0], 200)
        _, shared = self.call(self.login('admin')[0], 'files?scope=shared'); self.assertIn(meta['id'], [x['id'] for x in shared['files']])
        self.assertEqual(self.api('admin', 'files/delete', {'id': meta['id']})[0], 403)
        self.assertEqual(self.api('teacher', 'files/share', {'id': meta['id'], 'user_ids': []})[0], 200)
        self.assertEqual(self.raw_get('admin', 'files/download?id=' + meta['id'])[0], 403)
        self.assertEqual(self.api('teacher', 'files/share', {'id': meta['id'], 'user_ids': ['dev']})[0], 403)

    def test_upload_validation(self):
        self.assertEqual(self.upload('teacher', {'scope': 'personal'}, b'MZ' + b'0' * 50, 'tool.exe')[0], 400)
        self.assertEqual(self.upload('teacher', {'scope': 'personal'}, b'not really a pdf', 'fake.pdf')[0], 400)
        self.assertEqual(self.upload('teacher', {'scope': 'personal'}, PNG, '../../etc/passwd.png')[1].get('name'), 'passwd.png')
        try:  # the server may reset the connection instead of reading an oversized body
            self.assertEqual(self.upload('teacher', {'scope': 'personal'}, b'x' * (1024 * 1024 + 1), 'big.txt')[0], 413)
        except (urllib.error.URLError, ConnectionError):
            pass
        self.assertEqual(self.upload('teacher', {'scope': 'personal'}, b'', 'empty.txt')[0], 400)
        self.assertEqual(self.upload('nochat', {'scope': 'personal'}, PDF, 'a.pdf')[0], 403)
        self.assertEqual(self.upload('teacher', {'scope': 'bogus'}, PDF, 'a.pdf')[0], 400)
        op, _ = self.login('teacher')
        req = urllib.request.Request(self.base + '/api/files/upload?scope=personal&name=a.pdf', data=PDF, method='POST', headers={'Content-Type': 'application/pdf'})
        with self.assertRaises(urllib.error.HTTPError) as err:
            op.open(req)
        self.assertEqual(err.exception.code, 403)

    def test_department_and_company_libraries(self):
        self.assertEqual(self.upload('teacher', {'scope': 'department', 'department': 'Academy'}, PDF, 'Syllabus.pdf')[0], 403)
        status, meta = self.upload('teacher2', {'scope': 'department', 'department': 'Academy'}, PDF, 'Syllabus.pdf'); self.assertEqual(status, 201)
        self.assertEqual(self.raw_get('teacher', 'files/download?id=' + meta['id'])[0], 200)
        self.assertEqual(self.raw_get('dev', 'files/download?id=' + meta['id'])[0], 403)
        self.assertEqual(self.raw_get('nochat', 'files/download?id=' + meta['id'])[0], 403)
        self.assertEqual(self.api('teacher', 'files/delete', {'id': meta['id']})[0], 403)
        self.assertEqual(self.call(self.login('dev')[0], 'files?scope=department&department=Academy')[0], 403)
        self.assertEqual(self.upload('teacher2', {'scope': 'company'}, PDF, 'Handbook.pdf')[0], 403)
        self.assertEqual(self.upload('admin', {'scope': 'company'}, PDF, 'Handbook.pdf')[0], 201)
        _, listing = self.call(self.login('dev')[0], 'files?scope=company'); self.assertEqual([x['name'] for x in listing['files']], ['Handbook.pdf'])
        self.assertEqual(self.api('teacher2', 'files/comment', {'id': meta['id'], 'body': 'Please add week 4.'})[0], 200)
        _, detail = self.call(self.login('teacher')[0], 'files/detail?id=' + meta['id']); self.assertEqual(detail['comments'][0]['body'], 'Please add week 4.')
        self.assertEqual(self.api('teacher2', 'files/delete', {'id': meta['id']})[0], 200)
        self.assertEqual(self.raw_get('teacher', 'files/download?id=' + meta['id'])[0], 403)
        _, trash = self.call(self.login('teacher2')[0], 'files?scope=department&department=Academy&trash=1'); self.assertIn(meta['id'], [x['id'] for x in trash['files']])
        self.assertEqual(self.api('teacher2', 'files/restore', {'id': meta['id']})[0], 200)
        self.assertEqual(self.raw_get('teacher', 'files/download?id=' + meta['id'])[0], 200)

    def test_folders_move_rename_and_extension_rules(self):
        _, folder = self.api('teacher', 'files/folder', {'scope': 'personal', 'name': 'Contracts'})
        _, meta = self.upload('teacher', {'scope': 'personal', 'folder': folder['id']}, PDF, 'inside.pdf')
        _, top = self.call(self.login('teacher')[0], 'files?scope=personal'); self.assertIn(folder['id'], [x['id'] for x in top['folders']]); self.assertNotIn(meta['id'], [x['id'] for x in top['files']])
        _, inner = self.call(self.login('teacher')[0], 'files?scope=personal&folder=' + folder['id']); self.assertEqual([x['id'] for x in inner['files']], [meta['id']]); self.assertEqual(inner['breadcrumb'][0]['name'], 'Contracts')
        self.assertEqual(self.api('teacher', 'files/folder-delete', {'id': folder['id']})[0], 400)
        self.assertEqual(self.api('teacher', 'files/update', {'id': meta['id'], 'name': 'inside.exe'})[0], 400)
        self.assertEqual(self.api('teacher', 'files/update', {'id': meta['id'], 'name': 'renamed.pdf', 'folder_id': ''})[0], 200)
        self.assertEqual(self.api('dev', 'files/update', {'id': meta['id'], 'name': 'x.pdf'})[0], 403)
        self.assertEqual(self.api('dev', 'files/folder', {'scope': 'personal', 'parent_id': folder['id'], 'name': 'bad'})[0], 400)
        self.assertEqual(self.api('teacher', 'files/folder-delete', {'id': folder['id']})[0], 200)

    def test_chat_attachments_follow_channel_access(self):
        _, dm = self.api('teacher', 'chat/dm', {'user_id': 'admin'})
        status, meta = self.upload('teacher', {'scope': 'chat', 'channel': dm['channel']}, PNG, 'diagram.png'); self.assertEqual(status, 201)
        self.assertEqual(self.upload('dev', {'scope': 'chat', 'channel': dm['channel']}, PNG, 'x.png')[0], 403)
        self.assertEqual(self.raw_get('admin', 'files/download?id=' + meta['id'])[0], 403)  # unsent attachments are private to the uploader
        status, sent = self.send('teacher', dm['channel'], '', file_id=meta['id']); self.assertEqual(status, 200)
        code, body, headers = self.raw_get('admin', 'files/download?inline=1&id=' + meta['id']); self.assertEqual((code, body), (200, PNG)); self.assertIn('inline', headers['Content-Disposition'])
        self.assertEqual(self.raw_get('dev', 'files/download?id=' + meta['id'])[0], 403)
        self.assertEqual(self.send('teacher', dm['channel'], 'again', file_id=meta['id'])[0], 400)
        _, hist = self.call(self.login('admin')[0], 'chat/messages?channel=' + urllib.parse.quote(dm['channel']))
        self.assertEqual(next(m for m in hist['messages'] if m['id'] == sent['id'])['file']['name'], 'diagram.png')
        self.assertEqual(self.api('teacher', 'chat/delete', {'id': sent['id']})[0], 200)
        self.assertEqual(self.raw_get('admin', 'files/download?id=' + meta['id'])[0], 403)

    # ------------------------------------------------------------ discussions & search
    def test_discussion_topics_are_department_scoped(self):
        status, t = self.api('teacher', 'topic-create', {'department': 'Academy', 'title': 'Assessment calibration', 'body': 'How do we score project evidence?', 'category': 'Decision'}); self.assertEqual(status, 200)
        self.assertEqual(self.api('teacher', 'topic-create', {'department': 'Studio', 'title': 'x', 'body': 'y'})[0], 403)
        self.assertEqual(self.api('dev', 'topic-reply', {'id': t['id'], 'body': 'not mine'})[0], 403)
        self.assertEqual(self.call(self.login('dev')[0], 'topic?id=' + t['id'])[0], 403)
        self.assertEqual(self.api('teacher2', 'topic-reply', {'id': t['id'], 'body': 'Use the rubric.'})[0], 200)
        _, detail = self.call(self.login('teacher')[0], 'topic?id=' + t['id']); self.assertEqual(detail['replies'][0]['author_name'], 'teacher2')
        self.assertEqual(self.api('teacher2', 'topic-update', {'id': t['id'], 'status': 'Closed'})[0], 403)
        self.assertEqual(self.api('teacher', 'topic-update', {'id': t['id'], 'pinned': True})[0], 403)
        self.assertEqual(self.api('admin', 'topic-update', {'id': t['id'], 'pinned': True})[0], 200)
        self.assertEqual(self.api('teacher', 'topic-update', {'id': t['id'], 'status': 'Resolved'})[0], 200)
        _, ws = self.call(self.login('teacher')[0], 'workspace'); self.assertTrue(any('replied to your discussion' in n['title'] for n in ws['notifications']))
        _, listing = self.call(self.login('dev')[0], 'topics'); self.assertNotIn(t['id'], [x['id'] for x in listing['topics']])
        _, listing = self.call(self.login('admin')[0], 'topics'); self.assertEqual(listing['topics'][0]['id'], t['id'])

    def test_search_respects_access(self):
        self.upload('teacher', {'scope': 'personal'}, PDF, 'Zebra private plan.pdf')
        self.upload('teacher2', {'scope': 'department', 'department': 'Academy'}, PDF, 'Zebra syllabus.pdf')
        self.send('teacher', 'dept:Academy', 'zebra migration notes')
        _, mine = self.call(self.login('teacher')[0], 'search?q=zebra'); kinds = sorted(r['type'] for r in mine['results'])
        self.assertEqual(kinds, ['Document', 'Document', 'Message'])
        _, admin = self.call(self.login('admin')[0], 'search?q=zebra'); self.assertEqual(sorted(r['title'] for r in admin['results'] if r['type'] == 'Document'), ['Zebra syllabus.pdf'])
        _, dev = self.call(self.login('dev')[0], 'search?q=zebra'); self.assertEqual(dev['results'], [])
        self.assertEqual(self.call(self.login('teacher')[0], 'search?q=z')[1]['results'], [])
        self.assertEqual(self.call(urllib.request.build_opener(), 'search?q=zebra')[0], 401)

    def test_new_permissions_are_assignable_but_scoped(self):
        self.assertIn('files.personal', self.call(self.login('admin')[0], 'workspace')[1]['permission_catalog'])
        grants = [{'permission': 'files.upload', 'scope_type': 'assigned', 'scope_id': ''}]
        self.assertEqual(self.api('admin', 'permissions', {'user_id': 'dev', 'grants': grants})[0], 400)


if __name__ == '__main__':
    unittest.main()
