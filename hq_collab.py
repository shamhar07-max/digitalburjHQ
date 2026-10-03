"""HQ collaboration: chat channels, the document vault (R2), discussion topics and global search.

Every query path loads the caller's grants and the staff table once (Ctx) and decides access in
memory, because each database round trip costs real latency between the web host and Supabase."""
import datetime, hashlib, os, re, secrets, time, urllib.parse
import hq_features as f
import r2

MAX_UPLOAD = int(os.environ.get('HQ_MAX_UPLOAD_MB', '20')) * 1024 * 1024
PERSONAL_QUOTA = 500 * 1024 * 1024
TRASH_DAYS = 30
PRESENCE_TTL = 45
EMOJI = ['👍', '❤️', '😂', '🎉', '🙏', '👀', '✅', '🔥']
TOPIC_CATEGORIES = ['General', 'Decision', 'Question', 'Idea', 'Announcement', 'Incident']
f.PERMISSIONS.update({
 'files.view': 'Read department and company documents', 'files.upload': 'Upload department / company documents',
 'files.manage': 'Manage department / company documents', 'files.personal': 'Use a private personal document vault'})

OOXML = 'application/vnd.openxmlformats-officedocument.'
ODF = 'application/vnd.oasis.opendocument.'
FILE_TYPES = {
 'pdf': ('application/pdf', 'pdf'), 'png': ('image/png', 'png'), 'jpg': ('image/jpeg', 'jpg'), 'jpeg': ('image/jpeg', 'jpg'),
 'gif': ('image/gif', 'gif'), 'webp': ('image/webp', 'webp'),
 'docx': (OOXML + 'wordprocessingml.document', 'zip'), 'xlsx': (OOXML + 'spreadsheetml.sheet', 'zip'),
 'pptx': (OOXML + 'presentationml.presentation', 'zip'), 'odt': (ODF + 'text', 'zip'), 'ods': (ODF + 'spreadsheet', 'zip'),
 'odp': (ODF + 'presentation', 'zip'), 'zip': ('application/zip', 'zip'),
 'doc': ('application/msword', 'ole'), 'xls': ('application/vnd.ms-excel', 'ole'), 'ppt': ('application/vnd.ms-powerpoint', 'ole'),
 'txt': ('text/plain', 'text'), 'csv': ('text/csv', 'text'), 'md': ('text/markdown', 'text'), 'json': ('application/json', 'text'),
 'mp4': ('video/mp4', 'mp4'), 'mov': ('video/quicktime', 'mp4'), 'm4a': ('audio/mp4', 'mp4'), 'mp3': ('audio/mpeg', 'mp3'), 'wav': ('audio/wav', 'wav')}
INLINE = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'application/pdf'}


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='microseconds')


def uid():
    return secrets.token_hex(12)


def init(c):
    c.executescript('''
 CREATE TABLE IF NOT EXISTS channels(id TEXT PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,department TEXT NOT NULL DEFAULT '',created_by TEXT,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS channel_members(channel_id TEXT NOT NULL REFERENCES channels(id),user_id TEXT NOT NULL REFERENCES users(id),last_read TEXT NOT NULL DEFAULT '',PRIMARY KEY(channel_id,user_id));
 CREATE TABLE IF NOT EXISTS chat_messages(id TEXT PRIMARY KEY,channel_id TEXT NOT NULL REFERENCES channels(id),sender TEXT NOT NULL REFERENCES users(id),body TEXT NOT NULL,reply_to TEXT,file_id TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,edited INTEGER NOT NULL DEFAULT 0,deleted INTEGER NOT NULL DEFAULT 0,pinned INTEGER NOT NULL DEFAULT 0);
 CREATE INDEX IF NOT EXISTS chat_channel_updated ON chat_messages(channel_id,updated);
 CREATE INDEX IF NOT EXISTS chat_channel_created ON chat_messages(channel_id,created);
 CREATE TABLE IF NOT EXISTS chat_reactions(message_id TEXT NOT NULL REFERENCES chat_messages(id),user_id TEXT NOT NULL REFERENCES users(id),emoji TEXT NOT NULL,PRIMARY KEY(message_id,user_id,emoji));
 CREATE TABLE IF NOT EXISTS presence(user_id TEXT PRIMARY KEY REFERENCES users(id),seen REAL NOT NULL,typing_channel TEXT NOT NULL DEFAULT '',typing_until REAL NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS folders(id TEXT PRIMARY KEY,scope TEXT NOT NULL,department TEXT NOT NULL DEFAULT '',owner TEXT REFERENCES users(id),parent_id TEXT,name TEXT NOT NULL,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,scope TEXT NOT NULL,department TEXT NOT NULL DEFAULT '',owner TEXT NOT NULL REFERENCES users(id),folder_id TEXT,name TEXT NOT NULL,mime TEXT NOT NULL,size INTEGER NOT NULL,sha256 TEXT NOT NULL,r2_key TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',pinned INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL,updated TEXT NOT NULL,deleted_at TEXT);
 CREATE INDEX IF NOT EXISTS files_scope ON files(scope,department,folder_id);
 CREATE TABLE IF NOT EXISTS file_shares(file_id TEXT NOT NULL REFERENCES files(id),user_id TEXT NOT NULL REFERENCES users(id),created TEXT NOT NULL,PRIMARY KEY(file_id,user_id));
 CREATE TABLE IF NOT EXISTS file_comments(id TEXT PRIMARY KEY,file_id TEXT NOT NULL REFERENCES files(id),author TEXT NOT NULL REFERENCES users(id),body TEXT NOT NULL,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS topics(id TEXT PRIMARY KEY,department TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,author TEXT NOT NULL REFERENCES users(id),category TEXT NOT NULL DEFAULT 'General',pinned INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'Open',created TEXT NOT NULL,updated TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS topic_replies(id TEXT PRIMARY KEY,topic_id TEXT NOT NULL REFERENCES topics(id),author TEXT NOT NULL REFERENCES users(id),body TEXT NOT NULL,created TEXT NOT NULL);
 ''')


class Ctx:
    """The caller's grants and the staff table, loaded at most once per request."""

    def __init__(self, c, u):
        self.c, self.u = c, u
        self.owner = f.owner(u)
        self.grants = [] if self.owner else [dict(x) for x in c.execute('SELECT permission,scope_type,scope_id FROM grants WHERE user_id=?', (u['id'],))]
        self._users = None

    @property
    def users(self):
        if self._users is None:
            self._users = {x['id']: dict(x) for x in self.c.execute('SELECT id,name,email,department,role,active FROM users')}
        return self._users

    def any(self, p):
        return self.owner or any(g['permission'] == p for g in self.grants)

    def has(self, p, department=None, record_id=None, assigned=None):
        if self.owner:
            return True
        for g in self.grants:
            if g['permission'] != p:
                continue
            t = g['scope_type']
            if t == 'all' or (t == 'department' and department and g['scope_id'] == department) or (t == 'record' and record_id and g['scope_id'] == record_id) or (t == 'assigned' and assigned == self.u['id']):
                return True
        return False

    def can_message(self, target):
        return bool(target and target['active'] and (self.has('messages.use', target['department'], target['id']) or (self.any('messages.use') and target['email'] == f.OWNER)))

    def moderator(self, department):
        return self.owner or self.has('announcements.publish', department)


def clean(b, key, maxlen=4000, required=True):
    return f.clean(b, key, maxlen, required)


def like(q):
    """Pattern for `LOWER(column) LIKE ? ESCAPE` (case-insensitive on SQLite and PostgreSQL alike)."""
    return '%' + q.lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def display_name(raw):
    name = os.path.basename(str(raw).replace('\\', '/')).strip()
    name = re.sub(r'[\x00-\x1f<>:"|?*]', '', name)[:120]
    if not name or name.startswith('.') or '.' not in name:
        raise ValueError('Choose a file with a valid name and extension.')
    return name


# ---------------------------------------------------------------- chat

def dm_id(a, b):
    x, y = sorted([a, b])
    return 'dm:' + x + ':' + y


def peer_of(cid, me):
    parts = cid.split(':')[1:]
    return parts[0] if parts[1] == me else parts[1] if parts[0] == me else None


def channel_ok(ctx, ch):
    """Whether the caller may use this channel. `ch` carries `member` for membership-based kinds."""
    if not ch or not ctx.any('messages.use'):
        return False
    kind = ch['kind']
    if kind == 'company':
        return True
    if kind == 'department':
        return ctx.owner or ctx.u['department'] == ch['department'] or ctx.has('messages.use', ch['department'])
    if kind == 'dm':
        peer = peer_of(ch['id'], ctx.u['id'])
        return bool(peer and ctx.can_message(ctx.users.get(peer)))
    return bool(ch.get('member'))


def channels_for(ctx):
    me = ctx.u['id']
    rows = ctx.c.execute('''SELECT ch.id,ch.kind,ch.name,ch.department,ch.created_by,m.user_id AS member,COALESCE(m.last_read,'') AS last_read,
 (SELECT COUNT(*) FROM chat_messages x WHERE x.channel_id=ch.id AND x.deleted=0 AND x.sender!=? AND x.created>COALESCE(m.last_read,'')) AS unread,
 (SELECT MIN(p.last_read) FROM channel_members p WHERE p.channel_id=ch.id AND p.user_id!=?) AS peer_read,
 (SELECT z.id FROM chat_messages z WHERE z.channel_id=ch.id AND z.deleted=0 ORDER BY z.created DESC LIMIT 1) AS last_id
 FROM channels ch LEFT JOIN channel_members m ON m.channel_id=ch.id AND m.user_id=?
 WHERE ch.kind IN ('company','department') OR m.user_id IS NOT NULL''', (me, me, me)).fetchall()
    return [dict(r) for r in rows if channel_ok(ctx, dict(r))]


def one_channel(ctx, cid):
    row = ctx.c.execute('''SELECT ch.*,m.user_id AS member FROM channels ch LEFT JOIN channel_members m ON m.channel_id=ch.id AND m.user_id=? WHERE ch.id=?''', (ctx.u['id'], cid)).fetchone()
    ch = dict(row) if row else None
    return ch if channel_ok(ctx, ch) else None


def hydrate(c, rows, users):
    rows = [dict(r) for r in rows]
    if not rows:
        return rows
    ids = [r['id'] for r in rows]
    ph = ','.join('?' * len(ids))
    reactions = {}
    for x in c.execute('SELECT message_id,emoji,user_id FROM chat_reactions WHERE message_id IN (' + ph + ')', ids):
        reactions.setdefault(x['message_id'], {}).setdefault(x['emoji'], []).append(x['user_id'])
    file_ids = list({r['file_id'] for r in rows if r['file_id'] and not r['deleted']})
    files = {}
    if file_ids:
        for x in c.execute('SELECT id,name,mime,size FROM files WHERE id IN (' + ','.join('?' * len(file_ids)) + ') AND deleted_at IS NULL', file_ids):
            files[x['id']] = dict(x)
    reply_ids = list({r['reply_to'] for r in rows if r['reply_to']})
    replies = {}
    if reply_ids:
        for x in c.execute('SELECT id,sender,body,deleted FROM chat_messages WHERE id IN (' + ','.join('?' * len(reply_ids)) + ')', reply_ids):
            replies[x['id']] = {'id': x['id'], 'sender': x['sender'], 'body': '' if x['deleted'] else x['body'][:140], 'deleted': x['deleted']}
    for r in rows:
        r['reactions'] = reactions.get(r['id'], {})
        r['file'] = files.get(r['file_id']) if r['file_id'] else None
        r['reply'] = replies.get(r['reply_to']) if r['reply_to'] else None
        r['sender_name'] = users.get(r['sender'], {}).get('name', 'Former staff')
        if r['deleted']:
            r['body'] = ''
    return rows


def touch_presence(c, u, typing=None):
    now = time.time()
    c.execute('INSERT INTO presence(user_id,seen,typing_channel,typing_until) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET seen=excluded.seen', (u['id'], now, '', 0))
    if typing is not None:
        c.execute('UPDATE presence SET typing_channel=?,typing_until=? WHERE user_id=?', (typing, now + 5 if typing else 0, u['id']))


def presence_rows(c, me):
    now = time.time()
    online, typing = [], {}
    for x in c.execute('SELECT user_id,seen,typing_channel,typing_until FROM presence WHERE seen>? AND user_id!=?', (now - PRESENCE_TTL, me)):
        online.append(x['user_id'])
        if x['typing_until'] > now and x['typing_channel']:
            typing.setdefault(x['typing_channel'], []).append(x['user_id'])
    return online, typing


def ensure_channels(c):
    for cid, kind, name, dept in [('company', 'company', 'Company', '')] + [('dept:' + d, 'department', d, d) for d in f.DEPTS]:
        c.execute('INSERT OR IGNORE INTO channels(id,kind,name,department,created_by,created) VALUES(?,?,?,?,?,?)', (cid, kind, name, dept, None, stamp()))


def upsert_read(c, cid, user, when):
    c.execute('''INSERT INTO channel_members(channel_id,user_id,last_read) VALUES(?,?,?) ON CONFLICT(channel_id,user_id) DO UPDATE SET last_read=CASE WHEN excluded.last_read>channel_members.last_read THEN excluded.last_read ELSE channel_members.last_read END''', (cid, user, when))


def chat_bootstrap(c, u):
    ctx = Ctx(c, u)
    if not ctx.any('messages.use'):
        raise PermissionError('Messaging has not been assigned to your account.')
    ensure_channels(c)
    now = stamp()
    channels = channels_for(ctx)
    joined = False
    for ch in channels:
        if ch['kind'] in ('company', 'department') and not ch['member']:
            upsert_read(c, ch['id'], u['id'], now)
            joined = True
    if joined:
        channels = channels_for(ctx)
    touch_presence(c, u)
    last = {}
    ids = [x['last_id'] for x in channels if x['last_id']]
    if ids:
        for m in hydrate(c, c.execute('SELECT * FROM chat_messages WHERE id IN (' + ','.join('?' * len(ids)) + ')', ids).fetchall(), ctx.users):
            last[m['id']] = m
    people = [{'id': x['id'], 'name': x['name'], 'department': x['department'], 'role': x['role']} for x in ctx.users.values() if x['id'] != u['id'] and ctx.can_message(x)]
    for ch in channels:
        ch['last'] = last.get(ch['last_id'])
        if ch['kind'] == 'dm':
            ch['peer'] = peer_of(ch['id'], u['id'])
            ch['name'] = ctx.users.get(ch['peer'], {}).get('name', 'Former staff')
        if ch['kind'] == 'group':
            ch['members'] = [r['user_id'] for r in c.execute('SELECT user_id FROM channel_members WHERE channel_id=?', (ch['id'],))]
    online, typing = presence_rows(c, u['id'])
    return {'channels': channels, 'people': people, 'online': online, 'typing': typing, 'emoji': EMOJI, 'cursor': stamp(), 'me': u['id']}


def chat_sync(c, u, q):
    ctx = Ctx(c, u)
    if not ctx.any('messages.use'):
        raise PermissionError('Messaging has not been assigned to your account.')
    typing_in = q.get('typing')
    if typing_in and not one_channel(ctx, typing_in):
        typing_in = None
    touch_presence(c, u, typing_in)
    channels = channels_for(ctx)
    cursor = q.get('cursor', '')
    try:
        floor = (datetime.datetime.fromisoformat(cursor) - datetime.timedelta(seconds=3)).isoformat(timespec='microseconds')
    except ValueError:
        floor = ''
    changed, new_cursor = [], cursor or stamp()
    if channels and floor:
        ids = [x['id'] for x in channels]
        rows = c.execute('SELECT * FROM chat_messages WHERE updated>? AND channel_id IN (' + ','.join('?' * len(ids)) + ') ORDER BY updated LIMIT 300', [floor] + ids).fetchall()
        changed = hydrate(c, rows, ctx.users)
        if changed:
            new_cursor = max(new_cursor, max(m['updated'] for m in changed))
    online, typing = presence_rows(c, u['id'])
    allowed = {x['id'] for x in channels}
    summary = [{'id': x['id'], 'unread': x['unread'], 'peer_read': x['peer_read'] or '', 'last_id': x['last_id']} for x in channels]
    return {'cursor': new_cursor, 'messages': changed, 'channels': summary, 'online': online,
            'typing': {k: v for k, v in typing.items() if k in allowed}, 'total_unread': sum(x['unread'] for x in channels)}


def chat_messages(c, u, q):
    ctx = Ctx(c, u)
    ch = one_channel(ctx, q.get('channel', ''))
    if not ch:
        raise PermissionError('This conversation is not available to your account.')
    limit = min(max(int(q.get('limit', 40) or 40), 1), 100)
    before = q.get('before', '')
    rows = c.execute('SELECT * FROM chat_messages WHERE channel_id=?' + (' AND created<?' if before else '') + ' ORDER BY created DESC LIMIT ?',
                     [ch['id']] + ([before] if before else []) + [limit]).fetchall()
    return {'messages': hydrate(c, list(reversed(rows)), ctx.users), 'has_more': len(rows) == limit}


def mention_targets(ctx, ch, body):
    low = body.lower()
    out = []
    for p in ctx.users.values():
        if p['id'] != ctx.u['id'] and p['active'] and ('@' + p['name'].lower()) in low:
            out.append(p)
    return out


def peer_access(c, p, ch):
    """Whether staff member `p` can see channel `ch` (used before notifying them)."""
    person = c.execute('SELECT * FROM users WHERE id=?', (p['id'],)).fetchone()
    pc = Ctx(c, person)
    row = c.execute('SELECT ch.*,m.user_id AS member FROM channels ch LEFT JOIN channel_members m ON m.channel_id=ch.id AND m.user_id=? WHERE ch.id=?', (p['id'], ch['id'])).fetchone()
    return bool(row and channel_ok(pc, dict(row)))


def notify_chat(c, to, title, cid):
    if c.execute("SELECT 1 FROM notifications WHERE user_id=? AND resource='chat' AND record_id=? AND read_at IS NULL", (to, cid)).fetchone():
        return
    f.notify(c, to, title, 'chat', cid)


def chat_send(c, u, b):
    ctx = Ctx(c, u)
    ch = one_channel(ctx, b.get('channel', ''))
    if not ch:
        raise PermissionError('This conversation is not available to your account.')
    file_id = b.get('file_id') or None
    body = clean(b, 'body', 4000, required=not file_id)
    if file_id:
        fr = c.execute("SELECT * FROM files WHERE id=? AND scope='chat' AND department=? AND owner=? AND deleted_at IS NULL", (file_id, ch['id'], u['id'])).fetchone()
        if not fr or c.execute('SELECT 1 FROM chat_messages WHERE file_id=?', (file_id,)).fetchone():
            raise ValueError('That attachment is not available.')
    reply_to = b.get('reply_to') or None
    if reply_to and not c.execute('SELECT 1 FROM chat_messages WHERE id=? AND channel_id=?', (reply_to, ch['id'])).fetchone():
        raise ValueError('The message you are replying to is not in this conversation.')
    mid, now = uid(), stamp()
    c.execute('INSERT INTO chat_messages(id,channel_id,sender,body,reply_to,file_id,created,updated) VALUES(?,?,?,?,?,?,?,?)', (mid, ch['id'], u['id'], body, reply_to, file_id, now, now))
    upsert_read(c, ch['id'], u['id'], now)
    c.execute('UPDATE presence SET typing_until=0 WHERE user_id=?', (u['id'],))
    notified = set()
    if ch['kind'] == 'dm':
        peer = peer_of(ch['id'], u['id'])
        notified.add(peer)
        notify_chat(c, peer, 'New message from ' + u['name'] + '.', ch['id'])
    elif ch['kind'] == 'group':
        for r in c.execute('SELECT user_id FROM channel_members WHERE channel_id=? AND user_id!=?', (ch['id'], u['id'])).fetchall():
            notified.add(r['user_id'])
            notify_chat(c, r['user_id'], 'New message in ' + ch['name'] + '.', ch['id'])
    for p in mention_targets(ctx, ch, body):
        if p['id'] not in notified and peer_access(c, p, ch):
            f.notify(c, p['id'], u['name'] + ' mentioned you in ' + (ch['name'] if ch['kind'] != 'dm' else 'a message') + '.', 'chat', ch['id'])
    return {'id': mid, 'created': now}


def message_for_edit(c, ctx, mid):
    m = c.execute('SELECT * FROM chat_messages WHERE id=?', (mid,)).fetchone()
    ch = one_channel(ctx, m['channel_id']) if m else None
    if not m or not ch:
        raise PermissionError('This message is not available to your account.')
    return dict(m), ch


def chat_edit(c, u, b):
    ctx = Ctx(c, u)
    m, ch = message_for_edit(c, ctx, b.get('id'))
    if m['sender'] != u['id'] or m['deleted']:
        raise PermissionError('You can edit only your own messages.')
    c.execute('UPDATE chat_messages SET body=?,edited=1,updated=? WHERE id=?', (clean(b, 'body', 4000), stamp(), m['id']))
    return {'ok': True}


def chat_delete(c, u, b):
    ctx = Ctx(c, u)
    m, ch = message_for_edit(c, ctx, b.get('id'))
    moderator = ch['kind'] in ('company', 'department') and ctx.moderator(ch['department'] or 'All')
    if m['sender'] != u['id'] and not moderator:
        raise PermissionError('You can delete only your own messages.')
    c.execute("UPDATE chat_messages SET body='',deleted=1,pinned=0,updated=? WHERE id=?", (stamp(), m['id']))
    if m['file_id']:
        c.execute('UPDATE files SET deleted_at=?,updated=? WHERE id=?', (stamp(), stamp(), m['file_id']))
    if m['sender'] != u['id']:
        f.audit(c, u, 'Moderated a chat message', ch['id'])
    return {'ok': True}


def chat_react(c, u, b):
    ctx = Ctx(c, u)
    m, ch = message_for_edit(c, ctx, b.get('id'))
    emoji = b.get('emoji')
    if emoji not in EMOJI or m['deleted']:
        raise ValueError('Choose one of the available reactions.')
    if c.execute('SELECT 1 FROM chat_reactions WHERE message_id=? AND user_id=? AND emoji=?', (m['id'], u['id'], emoji)).fetchone():
        c.execute('DELETE FROM chat_reactions WHERE message_id=? AND user_id=? AND emoji=?', (m['id'], u['id'], emoji))
    else:
        c.execute('INSERT INTO chat_reactions VALUES(?,?,?)', (m['id'], u['id'], emoji))
    c.execute('UPDATE chat_messages SET updated=? WHERE id=?', (stamp(), m['id']))
    return {'ok': True}


def chat_pin(c, u, b):
    ctx = Ctx(c, u)
    m, ch = message_for_edit(c, ctx, b.get('id'))
    if m['deleted']:
        raise ValueError('Deleted messages cannot be pinned.')
    if ch['kind'] in ('company', 'department') and not ctx.moderator(ch['department'] or 'All'):
        raise PermissionError('Only moderators can pin messages in shared channels.')
    c.execute('UPDATE chat_messages SET pinned=?,updated=? WHERE id=?', (0 if m['pinned'] else 1, stamp(), m['id']))
    return {'ok': True}


def chat_read(c, u, b):
    ctx = Ctx(c, u)
    ch = one_channel(ctx, b.get('channel'))
    if not ch:
        raise PermissionError('This conversation is not available to your account.')
    upto = str(b.get('upto') or stamp())
    try:
        when = datetime.datetime.fromisoformat(upto)
    except ValueError:
        raise ValueError('Invalid read marker.')
    if not when.tzinfo:
        raise ValueError('Invalid read marker.')
    if when > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=2):
        upto = stamp()
    upsert_read(c, ch['id'], u['id'], upto)
    c.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND resource='chat' AND record_id=? AND read_at IS NULL", (f.now(), u['id'], ch['id']))
    return {'ok': True}


def chat_dm(c, u, b):
    ctx = Ctx(c, u)
    target = ctx.users.get(b.get('user_id'))
    if not target or target['id'] == u['id'] or not ctx.can_message(target):
        raise PermissionError('Messaging this person is outside your assigned access.')
    cid, now = dm_id(u['id'], target['id']), stamp()
    c.execute('INSERT OR IGNORE INTO channels(id,kind,name,department,created_by,created) VALUES(?,?,?,?,?,?)', (cid, 'dm', 'Direct message', '', u['id'], now))
    for person in (u['id'], target['id']):
        c.execute('INSERT OR IGNORE INTO channel_members(channel_id,user_id,last_read) VALUES(?,?,?)', (cid, person, now))
    return {'channel': cid}


def chat_group(c, u, b):
    ctx = Ctx(c, u)
    name = clean(b, 'name', 60)
    members = b.get('members', [])
    if not isinstance(members, list) or not 1 <= len(members) <= 30:
        raise ValueError('Choose between 1 and 30 people for the group.')
    now, cid = stamp(), uid()
    for pid in set(members):
        t = ctx.users.get(pid)
        if pid != u['id'] and not ctx.can_message(t):
            raise PermissionError('One of the selected people is outside your assigned access.')
    c.execute('INSERT INTO channels(id,kind,name,department,created_by,created) VALUES(?,?,?,?,?,?)', (cid, 'group', name, '', u['id'], now))
    for pid in set(members) | {u['id']}:
        c.execute('INSERT INTO channel_members(channel_id,user_id,last_read) VALUES(?,?,?)', (cid, pid, now))
        if pid != u['id']:
            f.notify(c, pid, u['name'] + ' added you to ' + name + '.', 'chat', cid)
    return {'channel': cid}


# ---------------------------------------------------------------- files

def file_row(c, fid):
    return c.execute('SELECT * FROM files WHERE id=?', (fid,)).fetchone()


def shared_with(c, fid, user_id):
    return bool(c.execute('SELECT 1 FROM file_shares WHERE file_id=? AND user_id=?', (fid, user_id)).fetchone())


def file_can(c, ctx, fr, action='view'):
    """Access rule per library. The HQ owner cannot read another person's personal vault."""
    if not fr:
        return False
    me = ctx.u['id']
    scope, dept = fr['scope'], fr['department']
    mine = fr['owner'] == me
    if scope == 'personal':
        if mine:
            return ctx.any('files.personal')
        return action == 'view' and ctx.any('files.personal') and shared_with(c, fr['id'], me)
    if scope == 'department':
        if action == 'view':
            return ctx.has('files.view', dept)
        return ctx.has('files.manage', dept) or (mine and ctx.has('files.upload', dept))
    if scope == 'company':
        if action == 'view':
            return ctx.any('files.view')
        return ctx.has('files.manage', 'All') or (mine and ctx.has('files.upload', 'All'))
    if scope == 'chat':
        ch = one_channel(ctx, dept)
        if not ch or (action != 'view' and not mine):
            return False
        # An uploaded attachment stays private to its uploader until it is sent in a message.
        return mine or bool(c.execute('SELECT 1 FROM chat_messages WHERE file_id=? AND deleted=0', (fr['id'],)).fetchone())
    return False


def library_ok(ctx, scope, dept, write=False):
    if scope == 'personal':
        return ctx.any('files.personal')
    if scope == 'department':
        return dept in f.DEPTS and (ctx.has('files.upload', dept) if write else ctx.has('files.view', dept))
    if scope == 'company':
        return ctx.has('files.upload', 'All') if write else ctx.any('files.view')
    return False


def sniff(kind, data):
    if kind == 'pdf':
        return data.startswith(b'%PDF-')
    if kind == 'png':
        return data.startswith(b'\x89PNG\r\n\x1a\n')
    if kind == 'jpg':
        return data.startswith(b'\xff\xd8\xff')
    if kind == 'gif':
        return data[:6] in (b'GIF87a', b'GIF89a')
    if kind == 'webp':
        return data[:4] == b'RIFF' and data[8:12] == b'WEBP'
    if kind == 'zip':
        return data.startswith(b'PK\x03\x04')
    if kind == 'ole':
        return data.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')
    if kind == 'text':
        if b'\x00' in data[:8192]:
            return False
        try:
            data[:65536].decode('utf-8')
            return True
        except UnicodeDecodeError:
            return len(data) > 65536
    if kind == 'mp4':
        return data[4:8] == b'ftyp'
    if kind == 'mp3':
        return data.startswith(b'ID3') or (len(data) > 1 and data[0] == 0xff and data[1] & 0xe0 == 0xe0)
    if kind == 'wav':
        return data[:4] == b'RIFF' and data[8:12] == b'WAVE'
    return False


def file_payload(fr, names=None, comments=0):
    d = {k: fr[k] for k in ['id', 'scope', 'department', 'owner', 'folder_id', 'name', 'mime', 'size', 'description', 'pinned', 'created', 'updated', 'deleted_at']}
    d['owner_name'] = (names or {}).get(fr['owner'], 'Former staff')
    d['previewable'] = fr['mime'] in INLINE
    d['comments'] = comments
    return d


def plan_upload(c, u, length, q):
    """Validate an upload request before any bytes are accepted. Returns the plan for store/record."""
    ctx = Ctx(c, u)
    if length <= 0 or length > MAX_UPLOAD:
        raise ValueError('Files must be between 1 byte and %d MB.' % (MAX_UPLOAD // 1048576))
    name = display_name(q.get('name', ''))
    ext = name.rsplit('.', 1)[1].lower()
    if ext not in FILE_TYPES:
        raise ValueError('This file type is not allowed. Upload documents, images, archives, audio or video.')
    scope, dept, folder = q.get('scope', ''), q.get('department', ''), q.get('folder') or None
    if scope == 'chat':
        ch = one_channel(ctx, q.get('channel', ''))
        if not ch:
            raise PermissionError('This conversation is not available to your account.')
        dept, folder = ch['id'], None
    elif scope in ('personal', 'department', 'company'):
        if scope != 'department':
            dept = '' if scope == 'personal' else 'All'
        if not library_ok(ctx, scope, dept, write=True):
            raise PermissionError('Uploading to this library has not been assigned to your account.')
    else:
        raise ValueError('Choose a document library.')
    if folder:
        fo = c.execute('SELECT * FROM folders WHERE id=?', (folder,)).fetchone()
        if not fo or fo['scope'] != scope or fo['department'] != dept or (scope == 'personal' and fo['owner'] != u['id']):
            raise ValueError('That folder is not available.')
    if scope == 'personal':
        used = c.execute("SELECT COALESCE(SUM(size),0) FROM files WHERE scope='personal' AND owner=? AND deleted_at IS NULL", (u['id'],)).fetchone()[0]
        if used + length > PERSONAL_QUOTA:
            raise ValueError('Your personal vault is full. Delete files to free space.')
    return {'name': name, 'ext': ext, 'mime': FILE_TYPES[ext][0], 'kind': FILE_TYPES[ext][1], 'scope': scope, 'department': dept, 'folder': folder, 'length': length}


def check_content(plan, data):
    if len(data) != plan['length'] or not sniff(plan['kind'], data):
        raise ValueError('The file content does not match its type, or the upload was incomplete.')


def record_upload(c, u, plan, key, data):
    fid, now = key.split('/')[-1], stamp()
    c.execute('INSERT INTO files(id,scope,department,owner,folder_id,name,mime,size,sha256,r2_key,description,pinned,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (fid, plan['scope'], plan['department'], u['id'], plan['folder'], plan['name'], plan['mime'], len(data), hashlib.sha256(data).hexdigest(), key, '', 0, now, now))
    if plan['scope'] != 'chat':
        f.audit(c, u, 'Uploaded document', plan['name'] + ' · ' + plan['scope'])
    return file_payload(file_row(c, fid), {u['id']: u['name']})


def purge_expired(c, limit=10):
    """Permanently remove documents that have sat in the trash past the retention period."""
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=TRASH_DAYS)).isoformat(timespec='microseconds')
    expired = c.execute('SELECT * FROM files WHERE deleted_at IS NOT NULL AND deleted_at<? LIMIT ?', (cutoff, limit)).fetchall()
    if not expired:
        return
    try:
        store = r2.files_store()
    except r2.StorageError:
        return
    for fr in expired:
        try:
            store.delete(fr['r2_key'])
        except r2.StorageError:
            continue
        for table in ('file_shares', 'file_comments'):
            c.execute('DELETE FROM ' + table + ' WHERE file_id=?', (fr['id'],))
        c.execute('DELETE FROM files WHERE id=?', (fr['id'],))


def files_list(c, u, q):
    ctx = Ctx(c, u)
    scope, dept = q.get('scope', 'personal'), q.get('department', '')
    folder_id, trash, search = q.get('folder') or None, q.get('trash') == '1', q.get('q', '').strip()
    names = {k: v['name'] for k, v in ctx.users.items()}
    if scope == 'shared':
        if not ctx.any('files.personal'):
            raise PermissionError('Your personal vault has not been enabled.')
        rows = c.execute('''SELECT x.* FROM files x JOIN file_shares s ON s.file_id=x.id WHERE s.user_id=? AND x.deleted_at IS NULL AND x.scope='personal' ORDER BY x.updated DESC LIMIT 200''', (u['id'],)).fetchall()
        return {'scope': scope, 'folders': [], 'files': [file_payload(r, names) for r in rows], 'breadcrumb': [], 'can_upload': False, 'can_manage': False}
    if scope not in ('personal', 'department', 'company') or not library_ok(ctx, scope, dept):
        raise PermissionError('This document library has not been assigned to your account.')
    if scope == 'company':
        dept = 'All'
    if scope == 'personal':
        dept = ''
    where = 'scope=? AND department=? AND deleted_at IS ' + ('NOT NULL' if trash else 'NULL')
    args = [scope, dept]
    if scope == 'personal':
        where += ' AND owner=?'
        args.append(u['id'])
    if search:
        where += " AND LOWER(name) LIKE ? ESCAPE '\\'"
        args.append(like(search))
    elif not trash:
        where += ' AND folder_id=?' if folder_id else ' AND folder_id IS NULL'
        if folder_id:
            args.append(folder_id)
    files = [r for r in c.execute('SELECT * FROM files WHERE ' + where + ' ORDER BY pinned DESC,name LIMIT 500', args).fetchall()]
    if trash:
        files = [r for r in files if file_can(c, ctx, r, 'edit')]
    counts = {}
    if files:
        ids = [r['id'] for r in files]
        for x in c.execute('SELECT file_id,COUNT(*) AS n FROM file_comments WHERE file_id IN (' + ','.join('?' * len(ids)) + ') GROUP BY file_id', ids):
            counts[x['file_id']] = x['n']
    folders, breadcrumb = [], []
    if not trash and not search:
        fargs = [scope, dept] + ([u['id']] if scope == 'personal' else []) + ([folder_id] if folder_id else [])
        folders = [dict(x) for x in c.execute('SELECT * FROM folders WHERE scope=? AND department=?' + (' AND owner=?' if scope == 'personal' else '') + (' AND parent_id=?' if folder_id else ' AND parent_id IS NULL') + ' ORDER BY name', fargs)]
        cur, guard = folder_id, 0
        while cur and guard < 12:
            fo = c.execute('SELECT * FROM folders WHERE id=? AND scope=? AND department=?', (cur, scope, dept)).fetchone()
            if not fo:
                break
            breadcrumb.insert(0, {'id': fo['id'], 'name': fo['name']})
            cur, guard = fo['parent_id'], guard + 1
    used = c.execute("SELECT COALESCE(SUM(size),0) FROM files WHERE scope='personal' AND owner=? AND deleted_at IS NULL", (u['id'],)).fetchone()[0] if scope == 'personal' else None
    manage = scope == 'personal' or library_ok(ctx, scope, dept, True) or ctx.has('files.manage', dept)
    purge_expired(c)
    return {'scope': scope, 'department': dept, 'folders': folders, 'breadcrumb': breadcrumb, 'trash': trash,
            'files': [file_payload(r, names, counts.get(r['id'], 0)) for r in files], 'can_upload': library_ok(ctx, scope, dept, True),
            'can_manage': manage, 'quota': {'used': used, 'limit': PERSONAL_QUOTA} if used is not None else None, 'trash_days': TRASH_DAYS}


def folder_write(c, ctx, b):
    scope, dept = b.get('scope'), b.get('department', '')
    if scope not in ('personal', 'department', 'company'):
        raise ValueError('Choose a document library.')
    dept = '' if scope == 'personal' else 'All' if scope == 'company' else dept
    if not library_ok(ctx, scope, dept, True):
        raise PermissionError('Creating folders in this library has not been assigned to your account.')
    parent = b.get('parent_id') or None
    if parent:
        pf = c.execute('SELECT * FROM folders WHERE id=?', (parent,)).fetchone()
        if not pf or pf['scope'] != scope or pf['department'] != dept or (scope == 'personal' and pf['owner'] != ctx.u['id']):
            raise ValueError('That parent folder is not available.')
    return scope, dept, parent


def file_post(c, u, path, b):
    ctx = Ctx(c, u)
    if path == 'files/folder':
        scope, dept, parent = folder_write(c, ctx, b)
        fid = uid()
        c.execute('INSERT INTO folders VALUES(?,?,?,?,?,?,?)', (fid, scope, dept, u['id'], parent, clean(b, 'name', 80), stamp()))
        return {'id': fid}
    if path == 'files/folder-delete':
        fo = c.execute('SELECT * FROM folders WHERE id=?', (b.get('id'),)).fetchone()
        if not fo:
            raise ValueError('Folder not found.')
        dept = fo['department']
        allowed = fo['owner'] == u['id'] and library_ok(ctx, fo['scope'], dept, True) if fo['scope'] == 'personal' else (ctx.has('files.manage', dept) or (fo['owner'] == u['id'] and library_ok(ctx, fo['scope'], dept, True)))
        if not allowed:
            raise PermissionError('You cannot delete this folder.')
        if c.execute('SELECT 1 FROM files WHERE folder_id=? AND deleted_at IS NULL', (fo['id'],)).fetchone() or c.execute('SELECT 1 FROM folders WHERE parent_id=?', (fo['id'],)).fetchone():
            raise ValueError('Move or delete the contents before deleting this folder.')
        c.execute('DELETE FROM folders WHERE id=?', (fo['id'],))
        return {'ok': True}
    fr = file_row(c, b.get('id'))
    if path == 'files/comment':
        if not file_can(c, ctx, fr, 'view') or fr['deleted_at']:
            raise PermissionError('This document is not available to your account.')
        body = clean(b, 'body', 2000)
        c.execute('INSERT INTO file_comments VALUES(?,?,?,?,?)', (uid(), fr['id'], u['id'], body, stamp()))
        for pid in {fr['owner']} - {u['id']}:
            if ctx.users.get(pid, {}).get('active') and fr['scope'] != 'chat':
                f.notify(c, pid, u['name'] + ' commented on ' + fr['name'] + '.', 'files', fr['id'])
        return {'ok': True}
    if path in ('files/restore', 'files/purge'):
        if not fr or not fr['deleted_at'] or not file_can(c, ctx, fr, 'edit'):
            raise PermissionError('This document is not available to your account.')
        if path == 'files/restore':
            c.execute('UPDATE files SET deleted_at=NULL,updated=? WHERE id=?', (stamp(), fr['id']))
        else:
            r2.files_store().delete(fr['r2_key'])
            for table in ('file_shares', 'file_comments'):
                c.execute('DELETE FROM ' + table + ' WHERE file_id=?', (fr['id'],))
            c.execute('DELETE FROM files WHERE id=?', (fr['id'],))
            f.audit(c, u, 'Permanently deleted document', fr['name'])
        return {'ok': True}
    if not fr or fr['deleted_at'] or not file_can(c, ctx, fr, 'edit' if path != 'files/share' else 'view'):
        raise PermissionError('This document is not available to your account.')
    if path == 'files/delete':
        c.execute('UPDATE files SET deleted_at=?,updated=? WHERE id=?', (stamp(), stamp(), fr['id']))
        f.audit(c, u, 'Moved document to trash', fr['name'])
        return {'ok': True}
    if path == 'files/update':
        name = display_name(b['name']) if b.get('name') else fr['name']
        if name.rsplit('.', 1)[1].lower() != fr['name'].rsplit('.', 1)[1].lower():
            raise ValueError('Keep the original file extension.')
        folder = b.get('folder_id', fr['folder_id']) or None
        if folder:
            fo = c.execute('SELECT * FROM folders WHERE id=?', (folder,)).fetchone()
            if not fo or fo['scope'] != fr['scope'] or fo['department'] != fr['department'] or (fr['scope'] == 'personal' and fo['owner'] != fr['owner']):
                raise ValueError('That folder is not available.')
        c.execute('UPDATE files SET name=?,description=?,folder_id=?,pinned=?,updated=? WHERE id=?', (name, clean(b, 'description', 500, False) if 'description' in b else fr['description'], folder, 1 if b.get('pinned', fr['pinned']) else 0, stamp(), fr['id']))
        return {'ok': True}
    if path == 'files/share':
        if fr['scope'] != 'personal' or fr['owner'] != u['id']:
            raise PermissionError('Only the owner can share a personal document.')
        ids = b.get('user_ids', [])
        if not isinstance(ids, list) or len(ids) > 30:
            raise ValueError('Choose up to 30 people.')
        c.execute('DELETE FROM file_shares WHERE file_id=?', (fr['id'],))
        for pid in set(ids) - {u['id']}:
            t = ctx.users.get(pid)
            if not t or not t['active'] or not ctx.can_message(t):
                raise PermissionError('One of the selected people is outside your assigned access.')
            c.execute('INSERT INTO file_shares VALUES(?,?,?)', (fr['id'], pid, stamp()))
            f.notify(c, pid, u['name'] + ' shared ' + fr['name'] + ' with you.', 'files', fr['id'])
        f.audit(c, u, 'Shared personal document', fr['name'])
        return {'ok': True}
    raise ValueError('Unknown document action.')


def file_detail(c, u, q):
    ctx = Ctx(c, u)
    fr = file_row(c, q.get('id'))
    if not file_can(c, ctx, fr, 'view') or fr['deleted_at']:
        raise PermissionError('This document is not available to your account.')
    names = {k: v['name'] for k, v in ctx.users.items()}
    comments = [{'id': x['id'], 'author': x['author'], 'author_name': names.get(x['author'], 'Former staff'), 'body': x['body'], 'created': x['created']} for x in c.execute('SELECT * FROM file_comments WHERE file_id=? ORDER BY created', (fr['id'],))]
    shares = [x['user_id'] for x in c.execute('SELECT user_id FROM file_shares WHERE file_id=?', (fr['id'],))] if fr['owner'] == u['id'] else []
    return {'file': file_payload(fr, names, len(comments)), 'comments': comments, 'shared_with': shares, 'can_edit': file_can(c, ctx, fr, 'edit')}


def download(c, u, q):
    """Authorise a download and return (store, row, inline) for the caller to deliver."""
    ctx = Ctx(c, u)
    fr = file_row(c, q.get('id'))
    if not file_can(c, ctx, fr, 'view') or fr['deleted_at']:
        raise PermissionError('This document is not available to your account.')
    inline = q.get('inline') == '1' and fr['mime'] in INLINE
    if fr['scope'] != 'chat' and not inline:
        f.audit(c, u, 'Downloaded document', fr['name'])
    return r2.files_store(), dict(fr), inline


# ---------------------------------------------------------------- discussions

def topic_ok(ctx, t):
    if not ctx.any('messages.use'):
        return False
    d = t['department']
    return d == 'All' or ctx.owner or ctx.u['department'] == d or ctx.has('messages.use', d)


def topics_list(c, u, q):
    ctx = Ctx(c, u)
    if not ctx.any('messages.use'):
        raise PermissionError('Discussions have not been assigned to your account.')
    rows = c.execute('SELECT t.*,(SELECT COUNT(*) FROM topic_replies r WHERE r.topic_id=t.id) AS replies FROM topics t ORDER BY t.pinned DESC,t.updated DESC LIMIT 200').fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if topic_ok(ctx, d):
            d['author_name'] = ctx.users.get(d['author'], {}).get('name', 'Former staff')
            d['can_moderate'] = d['author'] == u['id'] or ctx.moderator(d['department'])
            out.append(d)
    return {'topics': out, 'categories': TOPIC_CATEGORIES, 'departments': ['All'] + f.DEPTS}


def topic_detail(c, u, q):
    ctx = Ctx(c, u)
    t = c.execute('SELECT * FROM topics WHERE id=?', (q.get('id'),)).fetchone()
    if not t or not topic_ok(ctx, dict(t)):
        raise PermissionError('This discussion is not available to your account.')
    names = {k: v['name'] for k, v in ctx.users.items()}
    replies = [{**dict(x), 'author_name': names.get(x['author'], 'Former staff')} for x in c.execute('SELECT * FROM topic_replies WHERE topic_id=? ORDER BY created', (t['id'],))]
    topic = {**dict(t), 'author_name': names.get(t['author'], 'Former staff'), 'can_moderate': t['author'] == u['id'] or ctx.moderator(t['department'])}
    return {'topic': topic, 'replies': replies}


def topic_post(c, u, path, b):
    ctx = Ctx(c, u)
    if path == 'topic-create':
        dept = b.get('department', u['department'])
        probe = {'department': dept}
        if dept not in f.DEPTS + ['All'] or not topic_ok(ctx, probe):
            raise PermissionError('You cannot start a discussion in this audience.')
        category = b.get('category', 'General')
        if category not in TOPIC_CATEGORIES:
            raise ValueError('Choose a valid category.')
        tid, now = uid(), f.now()
        c.execute('INSERT INTO topics(id,department,title,body,author,category,pinned,status,created,updated) VALUES(?,?,?,?,?,?,0,?,?,?)', (tid, dept, clean(b, 'title', 160), clean(b, 'body', 8000), u['id'], category, 'Open', now, now))
        return {'id': tid}
    t = c.execute('SELECT * FROM topics WHERE id=?', (b.get('id'),)).fetchone()
    if not t or not topic_ok(ctx, dict(t)):
        raise PermissionError('This discussion is not available to your account.')
    if path == 'topic-reply':
        if t['status'] != 'Open':
            raise ValueError('This discussion is closed.')
        c.execute('INSERT INTO topic_replies VALUES(?,?,?,?,?)', (uid(), t['id'], u['id'], clean(b, 'body', 8000), f.now()))
        c.execute('UPDATE topics SET updated=? WHERE id=?', (f.now(), t['id']))
        if t['author'] != u['id']:
            f.notify(c, t['author'], u['name'] + ' replied to your discussion.', 'topics', t['id'])
        return {'ok': True}
    if path == 'topic-update':
        if t['author'] != u['id'] and not ctx.moderator(t['department']):
            raise PermissionError('Only the author or a moderator can change this discussion.')
        status = b.get('status', t['status'])
        if status not in ('Open', 'Resolved', 'Closed'):
            raise ValueError('Invalid status.')
        pinned = 1 if b.get('pinned', t['pinned']) else 0
        if pinned != t['pinned'] and not ctx.moderator(t['department']):
            raise PermissionError('Only moderators can pin discussions.')
        c.execute('UPDATE topics SET status=?,pinned=?,updated=? WHERE id=?', (status, pinned, f.now(), t['id']))
        return {'ok': True}
    raise ValueError('Unknown discussion action.')


# ---------------------------------------------------------------- search & notifications

def search(c, u, q):
    term = q.get('q', '').strip()
    if len(term) < 2:
        return {'results': []}
    ctx, pat, out = Ctx(c, u), like(term), []
    lo = term.lower()
    for p in ctx.users.values():
        if p['active'] and (p['id'] == u['id'] or ctx.has('people.view', p['department'], p['id'])) and (lo in p['name'].lower() or lo in p['email'].lower()):
            out.append({'type': 'Person', 'id': p['id'], 'title': p['name'], 'subtitle': p['department'] + ' · ' + p['role'], 'page': 'staff'})
    for t in c.execute("SELECT * FROM tasks WHERE LOWER(title) LIKE ? ESCAPE '\\' OR LOWER(description) LIKE ? ESCAPE '\\' LIMIT 40", (pat, pat)):
        if ctx.has('tasks.view', t['department'], t['id'], t['owner']):
            out.append({'type': 'Job', 'id': t['id'], 'title': t['title'], 'subtitle': t['department'] + ' · ' + t['status'], 'page': 'tasks'})
    shared = {x['file_id'] for x in c.execute('SELECT file_id FROM file_shares WHERE user_id=?', (u['id'],))}
    for fr in c.execute("SELECT * FROM files WHERE deleted_at IS NULL AND scope!='chat' AND (LOWER(name) LIKE ? ESCAPE '\\' OR LOWER(description) LIKE ? ESCAPE '\\') LIMIT 60", (pat, pat)):
        if fr['scope'] == 'personal':
            ok = (fr['owner'] == u['id'] or fr['id'] in shared) and ctx.any('files.personal')
        elif fr['scope'] == 'department':
            ok = ctx.has('files.view', fr['department'])
        else:
            ok = ctx.any('files.view')
        if ok:
            out.append({'type': 'Document', 'id': fr['id'], 'title': fr['name'], 'subtitle': {'personal': 'Personal vault', 'company': 'Company library'}.get(fr['scope'], fr['department'] + ' library'), 'page': 'files'})
    for t in c.execute("SELECT * FROM topics WHERE LOWER(title) LIKE ? ESCAPE '\\' OR LOWER(body) LIKE ? ESCAPE '\\' LIMIT 40", (pat, pat)):
        if topic_ok(ctx, dict(t)):
            out.append({'type': 'Discussion', 'id': t['id'], 'title': t['title'], 'subtitle': t['department'] + ' · ' + t['category'], 'page': 'discussions'})
    if ctx.any('messages.use'):
        channels = {x['id']: x for x in channels_for(ctx)}
        if channels:
            ids = list(channels)
            for m in c.execute("SELECT * FROM chat_messages WHERE deleted=0 AND LOWER(body) LIKE ? ESCAPE '\\' AND channel_id IN (" + ','.join('?' * len(ids)) + ') ORDER BY created DESC LIMIT 12', [pat] + ids):
                ch = channels[m['channel_id']]
                label = ctx.users.get(peer_of(ch['id'], u['id']), {}).get('name', 'Direct message') if ch['kind'] == 'dm' else ch['name']
                out.append({'type': 'Message', 'id': m['id'], 'title': m['body'][:90], 'subtitle': label, 'page': 'messages', 'channel': ch['id']})
    return {'results': out[:40]}


def notification_allowed(c, u, n):
    ctx = Ctx(c, u)
    if n['resource'] == 'chat':
        return bool(one_channel(ctx, n['record_id']))
    if n['resource'] == 'topics':
        t = c.execute('SELECT * FROM topics WHERE id=?', (n['record_id'],)).fetchone()
        return bool(t and topic_ok(ctx, dict(t)))
    if n['resource'] == 'files':
        fr = file_row(c, n['record_id'])
        return bool(fr and not fr['deleted_at'] and file_can(c, ctx, fr, 'view'))
    return False


# ---------------------------------------------------------------- HTTP routing

def query(h):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(h.path).query))


def get(h, c, u):
    path = urllib.parse.urlsplit(h.path).path
    routes = {'/api/chat/bootstrap': lambda q: chat_bootstrap(c, u), '/api/chat/sync': lambda q: chat_sync(c, u, q),
              '/api/chat/messages': lambda q: chat_messages(c, u, q), '/api/files': lambda q: files_list(c, u, q),
              '/api/files/detail': lambda q: file_detail(c, u, q), '/api/topics': lambda q: topics_list(c, u, q),
              '/api/topic': lambda q: topic_detail(c, u, q), '/api/search': lambda q: search(c, u, q)}
    if path != '/api/files/download' and path not in routes:
        return False
    if not u:
        h.send(401, {'error': 'Sign in to continue.'})
        return True
    try:
        if path == '/api/files/download':
            store, fr, inline = download(c, u, query(h))
            if store.local:
                data = store.get(fr['r2_key'])
                h.send_response(200)
                h.send_header('Content-Type', fr['mime'])
                h.send_header('Content-Length', str(len(data)))
                h.send_header('Content-Disposition', ('inline' if inline else 'attachment') + '; filename*=UTF-8\'\'' + urllib.parse.quote(fr['name']))
                h.send_header('X-Content-Type-Options', 'nosniff')
                h.send_header('Cache-Control', 'private, no-store')
                h.send_header('Content-Security-Policy', "default-src 'none'; sandbox")
                h.end_headers()
                h.wfile.write(data)
            else:
                h.send_response(302)
                h.send_header('Location', store.presigned_get(fr['r2_key'], 60, fr['name'], inline, fr['mime']))
                h.send_header('Cache-Control', 'private, no-store')
                h.end_headers()
        else:
            h.send(200, routes[path](query(h)))
    except PermissionError as e:
        h.send(403, {'error': str(e) or 'This action has not been assigned to your account.'})
    except r2.StorageError as e:
        h.send(502, {'error': 'Document storage is unavailable. ' + str(e)})
    return True


POSTS = {'chat/send': chat_send, 'chat/edit': chat_edit, 'chat/delete': chat_delete, 'chat/react': chat_react, 'chat/pin': chat_pin,
         'chat/read': chat_read, 'chat/dm': chat_dm, 'chat/group': chat_group}
FILE_POSTS = ['files/folder', 'files/folder-delete', 'files/comment', 'files/restore', 'files/purge', 'files/delete', 'files/update', 'files/share']
TOPIC_POSTS = ['topic-create', 'topic-reply', 'topic-update']


def post(h, c, u, b):
    path = h.path.removeprefix('/api/').split('?')[0]
    if path not in POSTS and path not in FILE_POSTS and path not in TOPIC_POSTS:
        return False
    try:
        if path in POSTS:
            result = POSTS[path](c, u, b)
        elif path in TOPIC_POSTS:
            result = topic_post(c, u, path, b)
        else:
            result = file_post(c, u, path, b)
        h.send(200, result)
    except PermissionError as e:
        h.send(403, {'error': str(e) or 'This action has not been assigned to your account.'})
    except r2.StorageError as e:
        h.send(502, {'error': 'Document storage is unavailable. ' + str(e)})
    return True
