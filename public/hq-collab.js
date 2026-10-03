'use strict';
/* HQ collaboration front end: shared helpers, demo backend, and the real-time messaging engine + UI.
   Relies on app.js globals (api, esc, initials, toast, formDialog, user, data, page, demo, owner, canAny)
   only at call time, so load order is hq-icons -> hq-collab -> hq-files -> hq-topics -> app. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const hueOf = id => { let h = 0; for (const c of String(id)) h = (h * 31 + c.charCodeAt(0)) >>> 0; return h % 360; };
const nameInitials = n => String(n || '?').split(/\s+/).map(x => x[0]).slice(0, 2).join('').toUpperCase();
const RICH_EMOJI = ['😀', '😄', '😂', '🙂', '😉', '😍', '🤔', '😮', '😢', '🙏', '👍', '👏', '🙌', '💪', '🎉', '🔥', '✅', '❤️', '👀', '🚀', '💡', '📌', '📎', '⏰'];

function avatar(p, { size = 38, online = false, cls = '' } = {}) {
  const person = p || { id: '?', name: '?' };
  return `<span class="av ${cls} ${online ? 'online' : ''}" data-hue="${hueOf(person.id)}" data-size="${size}">${esc(nameInitials(person.name))}<i class="on"></i></span>`;
}
function chanAvatar(ch, size = 38, online = false) {
  if (ch.kind === 'dm') return avatar({ id: ch.peer, name: ch.name }, { size, online });
  return `<span class="av ${ch.kind === 'group' ? 'group' : 'chan'}" data-size="${size}">${ico(ch.kind === 'group' ? 'users' : 'hash')}</span>`;
}
/* Apply values that CSP would block as inline styles, via custom properties. */
function paint(root = document) {
  $$('[data-hue]', root).forEach(el => el.style.setProperty('--h', el.dataset.hue));
  $$('[data-size]', root).forEach(el => el.style.setProperty('--s', el.dataset.size + 'px'));
  $$('[data-p]', root).forEach(el => el.style.setProperty('--p', el.dataset.p));
  $$('[data-i]', root).forEach(el => el.style.setProperty('--i', el.dataset.i));
}
function timeLabel(iso) {
  const d = new Date(iso), n = new Date();
  const days = Math.floor((new Date(n.getFullYear(), n.getMonth(), n.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
  if (days === 0) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (days === 1) return 'Yesterday';
  if (days < 7) return d.toLocaleDateString([], { weekday: 'short' });
  return d.toLocaleDateString([], { day: 'numeric', month: 'short' });
}
function dayLabel(iso) {
  const l = timeLabel(iso);
  if (/:/.test(l)) return 'Today';
  return l === 'Yesterday' ? l : new Date(iso).toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' });
}
const sameDay = (a, b) => new Date(a).toDateString() === new Date(b).toDateString();
function bytes(n) { return n < 1024 ? n + ' B' : n < 1048576 ? (n / 1024).toFixed(n < 10240 ? 1 : 0) + ' KB' : (n / 1048576).toFixed(1) + ' MB'; }
function richText(raw, people = []) {
  let t = esc(raw);
  t = t.replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/(https:\/\/[^\s<]+[^\s<.,;:!?)])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
  for (const p of [...people].sort((a, b) => b.name.length - a.name.length)) {
    const needle = '@' + esc(p.name);
    t = t.split(needle).join('<span class="mention">' + needle + '</span>');
  }
  return t;
}
function fileTypeOf(name, mime = '') {
  const e = String(name).split('.').pop().toLowerCase();
  if (e === 'pdf') return ['pdf', 'PDF'];
  if (['doc', 'docx', 'odt'].includes(e)) return ['doc', 'DOC'];
  if (['xls', 'xlsx', 'ods', 'csv'].includes(e)) return ['xls', e === 'csv' ? 'CSV' : 'XLS'];
  if (['ppt', 'pptx', 'odp'].includes(e)) return ['ppt', 'PPT'];
  if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(e)) return ['img', 'IMG'];
  if (['zip'].includes(e)) return ['zip', 'ZIP'];
  if (['mp4', 'mov', 'mp3', 'wav', 'm4a'].includes(e)) return ['med', e.toUpperCase().slice(0, 3)];
  return ['txt', e.toUpperCase().slice(0, 3) || 'FILE'];
}
const ftype = (name, mime, cls = '') => { const [t, l] = fileTypeOf(name, mime); return `<span class="ftype ${cls}" data-t="${t}">${esc(l)}</span>`; };

/* ---------------------------------------------------------------------------------
   Demo backend (sample preview only): the same endpoints, held in memory.
   --------------------------------------------------------------------------------- */
const DemoCollab = (() => {
  const st = { ready: false, cursor: 0, msgs: [], channels: [], lastRead: {}, peerRead: {}, typing: {}, files: [], folders: [], topics: [], replies: [], comments: [] };
  const iso = (offsetMin = 0) => new Date(Date.now() + offsetMin * 60000).toISOString();
  const rid = () => Math.random().toString(16).slice(2, 14);
  function init() {
    if (st.ready) return;
    st.ready = true;
    const me = user.id, staff = demoData.staff.filter(s => s.id !== me);
    st.channels = [{ id: 'company', kind: 'company', name: 'Company', department: '' }, { id: 'dept:' + user.department, kind: 'department', name: user.department, department: user.department }];
    staff.slice(0, 3).forEach(s => st.channels.push({ id: 'dm:' + [me, s.id].sort().join(':'), kind: 'dm', name: s.name, peer: s.id }));
    const add = (channel, sender, body, min, extra = {}) => st.msgs.push({ id: rid(), channel_id: channel, sender, body, created: iso(min), updated: iso(min), edited: 0, deleted: 0, pinned: 0, reply_to: null, file_id: null, reactions: {}, file: null, reply: null, ...extra });
    const nm = id => (demoData.staff.find(s => s.id === id) || {}).name;
    add('company', staff[0].id, 'Welcome to the new HQ. Messages, documents and discussions now live in one place.', -190);
    add('company', staff[1].id, 'Reminder: Friday release check at 15:00 — notes are in the Documents library.', -150, { reactions: { '👍': [staff[2].id, me], '🎉': [staff[0].id] } });
    add('dept:' + user.department, staff[2].id, 'Draft for the onboarding flow is ready for review.', -90);
    const dm1 = st.channels.find(c => c.kind === 'dm');
    add(dm1.id, dm1.peer, 'Hi! Could you look at the rubric when you have a minute?', -45);
    add(dm1.id, me, 'Sure — opening it now.', -40);
    add(dm1.id, dm1.peer, 'Thanks. I added two comments on the evidence section.', -12);
    st.channels.forEach(c => { st.lastRead[c.id] = c.id === dm1.id ? iso(-41) : iso(-1); st.peerRead[c.id] = iso(-30); });
    st.files = [
      { id: 'f1', scope: 'personal', department: '', owner: me, folder_id: null, name: 'My 2026 goals.docx', mime: 'application/msword', size: 48211, description: 'Private planning notes', pinned: 1, created: iso(-5000), updated: iso(-5000), deleted_at: null, owner_name: nm(me) || user.name, previewable: false, comments: 0 },
      { id: 'f2', scope: 'department', department: user.department, owner: staff[0].id, folder_id: null, name: 'Release checklist.pdf', mime: 'application/pdf', size: 182340, description: '', pinned: 1, created: iso(-3000), updated: iso(-300), deleted_at: null, owner_name: nm(staff[0].id), previewable: true, comments: 2 },
      { id: 'f3', scope: 'company', department: 'All', owner: staff[1].id, folder_id: null, name: 'Employee handbook.pdf', mime: 'application/pdf', size: 902117, description: 'Policies, leave and conduct', pinned: 0, created: iso(-9000), updated: iso(-9000), deleted_at: null, owner_name: nm(staff[1].id), previewable: true, comments: 0 },
      { id: 'f4', scope: 'company', department: 'All', owner: staff[1].id, folder_id: null, name: 'Brand guidelines.pptx', mime: 'application/vnd.ms-powerpoint', size: 3402117, description: '', pinned: 0, created: iso(-8000), updated: iso(-8000), deleted_at: null, owner_name: nm(staff[1].id), previewable: false, comments: 0 }
    ];
    st.folders = [{ id: 'fo1', scope: 'company', department: 'All', owner: staff[1].id, parent_id: null, name: 'Policies', created: iso(-9000) }];
    st.comments = [{ id: 'c1', file_id: 'f2', author: staff[1].id, author_name: nm(staff[1].id), body: 'Please add the rollback step.', created: iso(-280) }];
    st.topics = [
      { id: 't1', department: 'All', title: 'How should we handle weekend on-call?', body: 'Proposing a rotating schedule with a clear escalation path. Thoughts on fairness and coverage?', author: staff[0].id, author_name: nm(staff[0].id), category: 'Decision', pinned: 1, status: 'Open', created: iso(-2600), updated: iso(-200), replies: 2, can_moderate: owner() },
      { id: 't2', department: user.department, title: 'Template for client handover notes', body: 'Can we agree a single structure so nothing is lost between Studio and Business OS?', author: staff[2].id, author_name: nm(staff[2].id), category: 'Idea', pinned: 0, status: 'Open', created: iso(-900), updated: iso(-900), replies: 0, can_moderate: owner() }
    ];
    st.replies = [{ id: 'r1', topic_id: 't1', author: staff[1].id, author_name: nm(staff[1].id), body: 'A two-week rotation works well elsewhere. We should add a compensation note.', created: iso(-1500) }, { id: 'r2', topic_id: 't1', author: staff[2].id, author_name: nm(staff[2].id), body: 'Agree. Escalation to a manager after 20 minutes?', created: iso(-200) }];
  }
  const tick = () => String(++st.cursor).padStart(12, '0');
  function bump(m) { m.updated = new Date().toISOString(); m.rev = tick(); }
  const people = () => demoData.staff.filter(s => s.id !== user.id).map(s => ({ id: s.id, name: s.name, department: s.department, role: s.role }));
  const chanRows = () => st.channels.map(c => ({ ...c, member: user.id, last_read: st.lastRead[c.id] || '', peer_read: st.peerRead[c.id] || '',
    unread: st.msgs.filter(m => m.channel_id === c.id && !m.deleted && m.sender !== user.id && m.created > (st.lastRead[c.id] || '')).length,
    last_id: ([...st.msgs].reverse().find(m => m.channel_id === c.id && !m.deleted) || {}).id || null }));
  const autoReplies = ['Got it, thanks!', 'Looking at it now.', 'Great — let’s sync after lunch.', 'Perfect. I’ll update the doc.', '👍'];
  function simulateReply(m) {
    const ch = st.channels.find(c => c.id === m.channel_id);
    if (!ch || ch.kind !== 'dm') return;
    setTimeout(() => { st.typing[ch.id] = [ch.peer]; }, 900);
    setTimeout(() => {
      delete st.typing[ch.id];
      st.peerRead[ch.id] = new Date().toISOString();
      const r = { id: rid(), channel_id: ch.id, sender: ch.peer, body: autoReplies[Math.floor(Math.random() * autoReplies.length)], created: new Date().toISOString(), updated: new Date().toISOString(), edited: 0, deleted: 0, pinned: 0, reply_to: null, file_id: null, reactions: {}, file: null, reply: null };
      r.rev = tick(); st.msgs.push(r);
    }, 3200);
  }
  const hyd = m => ({ ...m, sender_name: (demoData.staff.find(s => s.id === m.sender) || {}).name || 'Former staff', reply: m.reply_to ? (() => { const r = st.msgs.find(x => x.id === m.reply_to); return r ? { id: r.id, sender: r.sender, body: r.deleted ? '' : r.body.slice(0, 140), deleted: r.deleted } : null; })() : null, file: m.file_id ? st.files.find(f => f.id === m.file_id) || null : null, body: m.deleted ? '' : m.body });
  async function handle(path, body) {
    init();
    const [route, qs] = path.split('?'), q = Object.fromEntries(new URLSearchParams(qs || ''));
    const fail = m => { throw Error(m); };
    switch (route) {
      case 'chat/bootstrap': return { channels: chanRows().map(c => ({ ...c, last: c.last_id ? hyd(st.msgs.find(m => m.id === c.last_id)) : null })), people: people(), online: people().slice(0, 2).map(p => p.id), typing: {}, emoji: ['👍', '❤️', '😂', '🎉', '🙏', '👀', '✅', '🔥'], cursor: new Date().toISOString(), me: user.id };
      case 'chat/sync': {
        const floor = q.cursor ? new Date(new Date(q.cursor).getTime() - 3000).toISOString() : '';
        const changed = floor ? st.msgs.filter(m => m.updated > floor).map(hyd) : [];
        return { cursor: new Date().toISOString(), messages: changed, channels: chanRows().map(c => ({ id: c.id, unread: c.unread, peer_read: c.peer_read, last_id: c.last_id, last_read: c.last_read })), online: people().slice(0, 2).map(p => p.id), typing: { ...st.typing }, total_unread: chanRows().reduce((n, c) => n + c.unread, 0) };
      }
      case 'chat/messages': { const l = st.msgs.filter(m => m.channel_id === q.channel && (!q.before || m.created < q.before)).sort((a, b) => a.created < b.created ? -1 : 1); return { messages: l.slice(-40).map(hyd), has_more: l.length > 40 }; }
      case 'chat/send': { if (!body.body && !body.file_id) fail('Enter body.'); const m = { id: rid(), channel_id: body.channel, sender: user.id, body: body.body || '', created: new Date().toISOString(), updated: new Date().toISOString(), edited: 0, deleted: 0, pinned: 0, reply_to: body.reply_to || null, file_id: body.file_id || null, reactions: {} }; st.msgs.push(m); st.lastRead[body.channel] = m.created; simulateReply(m); return { id: m.id, created: m.created }; }
      case 'chat/edit': { const m = st.msgs.find(x => x.id === body.id); if (!m || m.sender !== user.id) fail('You can edit only your own messages.'); m.body = body.body; m.edited = 1; bump(m); return { ok: true }; }
      case 'chat/delete': { const m = st.msgs.find(x => x.id === body.id); if (!m || (m.sender !== user.id && !owner())) fail('You can delete only your own messages.'); m.deleted = 1; m.body = ''; m.updated = new Date().toISOString(); return { ok: true }; }
      case 'chat/react': { const m = st.msgs.find(x => x.id === body.id); const a = m.reactions[body.emoji] || (m.reactions[body.emoji] = []); const i = a.indexOf(user.id); if (i >= 0) a.splice(i, 1); else a.push(user.id); if (!a.length) delete m.reactions[body.emoji]; m.updated = new Date().toISOString(); return { ok: true }; }
      case 'chat/pin': { const m = st.msgs.find(x => x.id === body.id); m.pinned = m.pinned ? 0 : 1; m.updated = new Date().toISOString(); return { ok: true }; }
      case 'chat/read': st.lastRead[body.channel] = body.upto || new Date().toISOString(); return { ok: true };
      case 'chat/dm': { const p = demoData.staff.find(s => s.id === body.user_id); const id = 'dm:' + [user.id, body.user_id].sort().join(':'); if (!st.channels.some(c => c.id === id)) { st.channels.push({ id, kind: 'dm', name: p.name, peer: p.id }); st.lastRead[id] = new Date().toISOString(); } return { channel: id }; }
      case 'chat/group': { const id = 'g:' + rid(); st.channels.push({ id, kind: 'group', name: body.name, members: [...body.members, user.id] }); st.lastRead[id] = new Date().toISOString(); return { channel: id }; }
      case 'files': {
        const trash = q.trash === '1', scope = q.scope || 'personal';
        let files = scope === 'shared' ? [] : st.files.filter(f => f.scope === scope && (scope !== 'department' || f.department === q.department) && !!f.deleted_at === trash && (q.q ? f.name.toLowerCase().includes(q.q.toLowerCase()) : (f.folder_id || '') === (q.folder || '')));
        const folders = trash || q.q || scope === 'shared' ? [] : st.folders.filter(f => f.scope === scope && (f.parent_id || '') === (q.folder || ''));
        const crumb = []; let cur = q.folder; while (cur) { const f = st.folders.find(x => x.id === cur); if (!f) break; crumb.unshift({ id: f.id, name: f.name }); cur = f.parent_id; }
        const used = st.files.filter(f => f.scope === 'personal' && !f.deleted_at).reduce((n, f) => n + f.size, 0);
        return { scope, department: q.department || '', folders, files, breadcrumb: crumb, trash, can_upload: scope !== 'shared', can_manage: true, quota: scope === 'personal' ? { used, limit: 500 * 1048576 } : null, trash_days: 30 };
      }
      case 'files/detail': { const f = st.files.find(x => x.id === q.id); return { file: f, comments: st.comments.filter(c => c.file_id === f.id), shared_with: [], can_edit: true }; }
      case 'files/folder': { const id = rid(); st.folders.push({ id, scope: body.scope, department: body.scope === 'department' ? body.department : body.scope === 'company' ? 'All' : '', owner: user.id, parent_id: body.parent_id || null, name: body.name, created: iso() }); return { id }; }
      case 'files/folder-delete': st.folders = st.folders.filter(f => f.id !== body.id); return { ok: true };
      case 'files/update': { const f = st.files.find(x => x.id === body.id); Object.assign(f, { name: body.name || f.name, description: body.description ?? f.description, folder_id: body.folder_id === undefined ? f.folder_id : (body.folder_id || null), pinned: body.pinned === undefined ? f.pinned : (body.pinned ? 1 : 0) }); return { ok: true }; }
      case 'files/delete': st.files.find(x => x.id === body.id).deleted_at = iso(); return { ok: true };
      case 'files/restore': st.files.find(x => x.id === body.id).deleted_at = null; return { ok: true };
      case 'files/purge': st.files = st.files.filter(x => x.id !== body.id); return { ok: true };
      case 'files/share': return { ok: true };
      case 'files/comment': st.comments.push({ id: rid(), file_id: body.id, author: user.id, author_name: user.name, body: body.body, created: iso() }); return { ok: true };
      case 'topics': return { topics: st.topics.map(t => ({ ...t, replies: st.replies.filter(r => r.topic_id === t.id).length })), categories: ['General', 'Decision', 'Question', 'Idea', 'Announcement', 'Incident'], departments: ['All', ...depts] };
      case 'topic': { const t = st.topics.find(x => x.id === q.id); return { topic: t, replies: st.replies.filter(r => r.topic_id === t.id) }; }
      case 'topic-create': { const id = rid(); st.topics.unshift({ id, department: body.department, title: body.title, body: body.body, author: user.id, author_name: user.name, category: body.category, pinned: 0, status: 'Open', created: iso(), updated: iso(), replies: 0, can_moderate: true }); return { id }; }
      case 'topic-reply': { st.replies.push({ id: rid(), topic_id: body.id, author: user.id, author_name: user.name, body: body.body, created: iso() }); st.topics.find(t => t.id === body.id).updated = iso(); return { ok: true }; }
      case 'topic-update': { const t = st.topics.find(x => x.id === body.id); if (body.status) t.status = body.status; if (body.pinned !== undefined) t.pinned = body.pinned ? 1 : 0; return { ok: true }; }
      case 'search': {
        const t = (q.q || '').toLowerCase(); if (t.length < 2) return { results: [] };
        const out = [];
        st.files.filter(f => !f.deleted_at && f.name.toLowerCase().includes(t)).forEach(f => out.push({ type: 'Document', id: f.id, title: f.name, subtitle: f.scope === 'personal' ? 'Personal vault' : f.department + ' library', page: 'files' }));
        st.topics.filter(x => x.title.toLowerCase().includes(t)).forEach(x => out.push({ type: 'Discussion', id: x.id, title: x.title, subtitle: x.department + ' · ' + x.category, page: 'discussions' }));
        st.msgs.filter(m => !m.deleted && m.body.toLowerCase().includes(t)).slice(-6).forEach(m => out.push({ type: 'Message', id: m.id, title: m.body.slice(0, 90), subtitle: (st.channels.find(c => c.id === m.channel_id) || {}).name, page: 'messages', channel: m.channel_id }));
        demoData.staff.filter(s => s.name.toLowerCase().includes(t)).forEach(s => out.push({ type: 'Person', id: s.id, title: s.name, subtitle: s.department, page: 'staff' }));
        return { results: out };
      }
    }
    fail('Not available in the sample preview.');
  }
  function fakeUpload(file, scope, folder, dept) {
    init();
    const id = rid(), isImg = file.type.startsWith('image/');
    const rec = { id, scope, department: scope === 'department' ? dept : scope === 'company' ? 'All' : '', owner: user.id, folder_id: folder || null, name: file.name, mime: file.type || 'application/octet-stream', size: file.size, description: '', pinned: 0, created: iso(), updated: iso(), deleted_at: null, owner_name: user.name, previewable: isImg || file.type === 'application/pdf', comments: 0 };
    st.files.push(rec);
    return rec;
  }
  return { handle, fakeUpload, state: st };
})();

function collab(path, body) { return demo ? DemoCollab.handle(path, body) : api(path, body); }

/* XHR upload with progress. Resolves with the file record. */
function uploadFile(file, params, onProgress) {
  if (demo) {
    return new Promise(resolve => {
      let p = 0;
      const t = setInterval(() => { p += 18 + Math.random() * 22; onProgress(Math.min(p, 100)); if (p >= 100) { clearInterval(t); resolve(DemoCollab.fakeUpload(file, params.scope, params.folder, params.department)); } }, 140);
    });
  }
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open('POST', '/api/files/upload?' + new URLSearchParams({ ...params, name: file.name }));
    x.setRequestHeader('X-CSRF-Token', csrf);
    x.setRequestHeader('Content-Type', 'application/octet-stream');
    x.upload.onprogress = e => e.lengthComputable && onProgress(e.loaded / e.total * 100);
    x.onload = () => { let j = {}; try { j = JSON.parse(x.responseText); } catch { /* non-JSON error page */ } x.status === 201 ? resolve(j) : reject(Error(j.error || 'Upload failed (' + x.status + ').')); };
    x.onerror = () => reject(Error('Upload failed. Check your connection and try again.'));
    x.send(file);
  });
}
const fileUrl = (id, inline) => '/api/files/download?id=' + encodeURIComponent(id) + (inline ? '&inline=1' : '');

/* ---------------------------------------------------------------------------------
   Messaging engine
   --------------------------------------------------------------------------------- */
const Chat = {
  booted: false, booting: null, uid: '', channels: [], people: [], online: new Set(), typing: {}, emoji: [], cursor: '', me: '',
  msgs: {}, hasMore: {}, active: null, view: 'list', filter: '', drafts: {}, rendered: {}, unreadFrom: {}, notified: new Set(),
  timer: null, syncing: false, typingChannel: '', typingUntil: 0, typingCleared: true, reply: null, editing: null, files: [], bootAt: 0, readTimer: null, failures: 0,

  reset() { Object.assign(this, { booted: false, booting: null, channels: [], people: [], msgs: {}, hasMore: {}, active: null, drafts: {}, rendered: {}, notified: new Set(), cursor: '' }); clearTimeout(this.timer); },
  allowed() { return typeof canAny === 'function' && canAny('messages.use'); },
  async ensure() {
    if (!this.allowed()) return;
    if (this.uid !== user.id) { this.reset(); this.uid = user.id; }
    if (this.booted) return;
    if (!this.booting) this.booting = this.boot().finally(() => { this.booting = null; });
    return this.booting;
  },
  async boot() {
    const d = await collab('chat/bootstrap');
    Object.assign(this, { channels: d.channels, people: d.people, emoji: d.emoji, cursor: d.cursor, me: d.me, online: new Set(d.online), typing: d.typing, booted: true, bootAt: Date.now() });
    d.channels.forEach(c => { if (c.last) this.upsert(c.last, true); });
    this.updateBadges();
    this.schedule();
    if (page === 'messages') this.renderAll();
  },
  interval() {
    if (document.hidden) return 45000;
    return page === 'messages' ? (this.typingChannel ? 1200 : 1800) : 15000;
  },
  schedule() { clearTimeout(this.timer); if (this.booted && user) this.timer = setTimeout(() => this.sync(), this.interval()); },
  async sync() {
    if (this.syncing || !this.booted || !user) return;
    this.syncing = true;
    try {
      const q = new URLSearchParams({ cursor: this.cursor });
      if (this.typingChannel && Date.now() < this.typingUntil) { q.set('typing', this.typingChannel); this.typingCleared = false; }
      else if (!this.typingCleared) { q.set('typing', ''); this.typingCleared = true; }
      this.apply(await collab('chat/sync?' + q));
      this.failures = 0;
    } catch (e) { this.failures++; if (e.message && /Messaging has not/.test(e.message)) return; }
    finally { this.syncing = false; this.schedule(); }
  },
  apply(d) {
    this.cursor = d.cursor > this.cursor ? d.cursor : this.cursor;
    this.online = new Set(d.online);
    this.typing = d.typing || {};
    let needBoot = false, activeChanged = false;
    for (const s of d.channels) {
      const ch = this.channels.find(c => c.id === s.id);
      if (!ch) { needBoot = true; continue; }
      Object.assign(ch, s);
    }
    this.channels = this.channels.filter(c => d.channels.some(s => s.id === c.id));
    for (const m of d.messages) {
      const fresh = !this.find(m.channel_id, m.id);
      this.upsert(m);
      if (m.channel_id === this.active) activeChanged = true;
      if (fresh && m.sender !== this.me && !m.deleted && m.created > new Date(this.bootAt - 1000).toISOString() && !this.notified.has(m.id)) {
        this.notified.add(m.id);
        if (!(page === 'messages' && m.channel_id === this.active && !document.hidden)) this.incoming(m);
      }
    }
    if (needBoot) { this.rebootstrap(); }
    this.updateBadges();
    if (page === 'messages') { this.renderList(); if (activeChanged || this.typingSig() !== this.lastTypingSig) { this.lastTypingSig = this.typingSig(); this.renderThread(); } this.renderHeader(); this.maybeRead(); }
  },
  typingSig() { return JSON.stringify(this.typing[this.active] || []) + JSON.stringify(this.channels.find(c => c.id === this.active)?.peer_read || ''); },
  async rebootstrap() { try { const d = await collab('chat/bootstrap'); this.channels = d.channels; this.people = d.people; this.updateBadges(); if (page === 'messages') this.renderList(); } catch { /* retried by next sync */ } },
  incoming(m) {
    const ch = this.channels.find(c => c.id === m.channel_id);
    const label = ch ? (ch.kind === 'dm' ? ch.name : ch.name + ' · ' + m.sender_name) : m.sender_name;
    toast(label + ': ' + (m.body || 'Sent an attachment').slice(0, 90), () => { this.open(m.channel_id); if (page !== 'messages') { page = 'messages'; render(); } });
  },
  updateBadges() {
    const total = this.channels.reduce((n, c) => n + (c.unread || 0), 0);
    this.total = total;
    if (data) data.unread_chat = total;
    document.title = (total ? '(' + total + ') ' : '') + 'Headquarters · DigitalBurj';
    $$('[data-badge=messages]').forEach(el => { el.textContent = total > 99 ? '99+' : total; el.hidden = !total; });
  },
  find(cid, id) { return (this.msgs[cid] || []).find(m => m.id === id); },
  upsert(m, silent) {
    const list = this.msgs[m.channel_id] || (this.msgs[m.channel_id] = []);
    // An optimistic copy of this very message is replaced instead of duplicated.
    if (m.sender === this.me) {
      const tmp = list.findIndex(x => x.pending && x.body === m.body && !!x.file === !!m.file);
      if (tmp >= 0 && !list.some(x => x.id === m.id)) list.splice(tmp, 1);
    }
    const i = list.findIndex(x => x.id === m.id);
    if (i >= 0) list[i] = { ...list[i], ...m, pending: false, failed: false };
    else { list.push(m); list.sort((a, b) => a.created < b.created ? -1 : a.created > b.created ? 1 : 0); }
  },
  person(id) { return this.people.find(p => p.id === id) || (id === this.me ? { id, name: user.name } : { id, name: 'Former staff' }); },
  channel(id) { return this.channels.find(c => c.id === id); },
  senderName(m) { return m.sender_name || this.person(m.sender).name; },

  /* ----- opening, loading, reading ----- */
  async open(cid) {
    const ch = this.channel(cid);
    if (!ch) return;
    this.active = cid; this.view = 'thread'; this.reply = null; this.editing = null; this.files = [];
    this.unreadFrom[cid] = ch.last_read || '';
    this.rendered[cid] = new Set();
    this.typingChannel = '';
    if (page === 'messages') { this.renderAll(); }
    if (!this.msgs[cid] || !this.msgs[cid].length || !this.loaded?.[cid]) {
      try {
        const d = await collab('chat/messages?channel=' + encodeURIComponent(cid));
        (this.loaded = this.loaded || {})[cid] = true;
        this.hasMore[cid] = d.has_more;
        d.messages.forEach(m => this.upsert(m));
      } catch (e) { toast(e.message); }
    }
    if (this.active === cid && page === 'messages') { this.renderThread({ toUnread: true }); this.renderHeader(); this.maybeRead(300); }
  },
  async loadOlder() {
    const list = this.msgs[this.active] || [];
    if (!this.hasMore[this.active] || !list.length || this.loadingOlder) return;
    this.loadingOlder = true;
    try {
      const d = await collab('chat/messages?channel=' + encodeURIComponent(this.active) + '&before=' + encodeURIComponent(list[0].created));
      this.hasMore[this.active] = d.has_more;
      const th = $('#thread'), before = th ? th.scrollHeight : 0;
      d.messages.forEach(m => this.upsert(m));
      this.rendered[this.active] = new Set((this.msgs[this.active] || []).map(m => m.id));
      this.renderThread({ keep: true });
      if (th) th.scrollTop = th.scrollHeight - before;
    } finally { this.loadingOlder = false; }
  },
  maybeRead(delay = 700) {
    const ch = this.channel(this.active);
    if (!ch || !ch.unread || document.hidden || page !== 'messages') return;
    clearTimeout(this.readTimer);
    this.readTimer = setTimeout(async () => {
      const list = this.msgs[this.active] || [];
      const upto = list.length ? list[list.length - 1].created : null;
      if (!upto) return;
      ch.unread = 0; ch.last_read = upto;
      this.updateBadges(); this.renderList();
      try { await collab('chat/read', { channel: ch.id, upto }); } catch { /* next sync reconciles */ }
    }, delay);
  },

  /* ----- sending ----- */
  async send() {
    const ta = $('#chat-input');
    if (!ta || !this.active) return;
    const body = ta.value.trim();
    if (this.editing) return this.saveEdit(body);
    const ready = this.files.filter(f => f.id);
    if ((!body && !ready.length) || this.files.some(f => f.uploading)) return;
    const cid = this.active, reply = this.reply, queue = ready.length ? ready : [null];
    ta.value = ''; this.drafts[cid] = ''; this.autosize(); this.files = []; this.reply = null; this.typingChannel = '';
    this.renderComposerBars();
    queue.forEach((f, i) => this.post(cid, i === 0 ? body : '', f, i === 0 ? reply : null));
  },
  async post(cid, body, file, reply) {
    const tmp = { id: 'tmp-' + Math.random().toString(16).slice(2), channel_id: cid, sender: this.me, sender_name: user.name, body, reply_to: reply ? reply.id : null, reply: reply ? { id: reply.id, sender: reply.sender, body: reply.body.slice(0, 140) } : null, file: file ? { id: file.id, name: file.name, mime: file.mime, size: file.size } : null, file_id: file ? file.id : null, created: new Date().toISOString(), updated: new Date().toISOString(), reactions: {}, pending: true, edited: 0, deleted: 0, pinned: 0 };
    (this.msgs[cid] = this.msgs[cid] || []).push(tmp);
    this.renderThread({ stick: true }); this.renderList();
    try {
      const r = await collab('chat/send', { channel: cid, body, reply_to: tmp.reply_to, file_id: tmp.file_id });
      const list = this.msgs[cid], i = list.findIndex(x => x.id === tmp.id);
      const exists = list.some(x => x.id === r.id);
      if (i >= 0) { if (exists) list.splice(i, 1); else list[i] = { ...tmp, id: r.id, created: r.created, updated: r.created, pending: false }; }
      const ch = this.channel(cid); if (ch) { ch.last_id = r.id; ch.last_read = r.created; }
    } catch (e) { tmp.pending = false; tmp.failed = true; toast(e.message); }
    this.renderThread({ stick: true }); this.renderList();
  },
  retry(id) {
    const list = this.msgs[this.active] || [], i = list.findIndex(m => m.id === id);
    if (i < 0) return;
    const [m] = list.splice(i, 1);
    this.post(m.channel_id, m.body, m.file ? { id: m.file.id, name: m.file.name, mime: m.file.mime, size: m.file.size } : null, m.reply ? m.reply : null);
  },
  async saveEdit(body) {
    const id = this.editing; if (!body) return;
    this.editing = null; $('#chat-input').value = ''; this.drafts[this.active] = ''; this.autosize(); this.renderComposerBars();
    const m = this.find(this.active, id); if (m) { m.body = body; m.edited = 1; this.renderThread({ keep: true }); }
    try { await collab('chat/edit', { id, body }); } catch (e) { toast(e.message); }
  },
  async react(id, emoji) {
    const m = this.find(this.active, id); if (!m || m.pending) return;
    const a = m.reactions[emoji] || (m.reactions[emoji] = []), i = a.indexOf(this.me);
    if (i >= 0) a.splice(i, 1); else a.push(this.me);
    if (!a.length) delete m.reactions[emoji];
    this.flashReact = emoji + id;
    this.renderThread({ keep: true });
    try { await collab('chat/react', { id, emoji }); } catch (e) { toast(e.message); }
  },
  async attach(fileList) {
    const cid = this.active; if (!cid) return;
    for (const file of fileList) {
      if (file.size > 20 * 1048576) { toast(file.name + ' is larger than 20 MB.'); continue; }
      const rec = { name: file.name, size: file.size, progress: 0, uploading: true, mime: file.type, key: Math.random() };
      this.files.push(rec); this.renderComposerBars();
      uploadFile(file, { scope: 'chat', channel: cid }, p => { rec.progress = p; this.paintFiles(); })
        .then(meta => { Object.assign(rec, { id: meta.id, mime: meta.mime, uploading: false, progress: 100 }); this.renderComposerBars(); })
        .catch(e => { toast(e.message); this.files = this.files.filter(f => f !== rec); this.renderComposerBars(); });
    }
  },

  /* ----- rendering ----- */
  chName(ch) { return ch.kind === 'dm' ? ch.name : (ch.kind === 'department' ? ch.name + ' team' : ch.name); },
  isOnline(ch) { return ch.kind === 'dm' && this.online.has(ch.peer); },
  lastOf(ch) { const l = this.msgs[ch.id]; return (l && l.length ? l[l.length - 1] : null) || ch.last; },
  listHtml() {
    const f = this.filter.trim().toLowerCase();
    const sorted = [...this.channels].sort((a, b) => { const x = this.lastOf(a)?.created || '', y = this.lastOf(b)?.created || ''; return x < y ? 1 : x > y ? -1 : 0; });
    const item = ch => {
      const last = this.lastOf(ch), un = ch.unread || 0;
      const who = last ? (last.sender === this.me ? 'You: ' : (ch.kind === 'dm' ? '' : this.senderName(last).split(' ')[0] + ': ')) : '';
      const prev = last ? (last.deleted ? 'Message deleted' : who + (last.body || (last.file ? '📎 ' + last.file.name : ''))) : 'No messages yet';
      return `<button class="chat-item ${ch.id === this.active ? 'active' : ''} ${un ? 'has-unread' : ''}" data-chat="${esc(ch.id)}">${chanAvatar(ch, 42, this.isOnline(ch))}<span class="meta"><span class="row1"><b>${esc(this.chName(ch))}</b>${last ? `<time>${esc(timeLabel(last.created))}</time>` : ''}</span><span class="row2"><span class="prev">${this.typing[ch.id]?.length ? '<i class="typing-line">typing…</i>' : esc(prev)}</span>${un ? `<span class="unread">${un > 99 ? '99+' : un}</span>` : ''}</span></span></button>`;
    };
    const match = ch => !f || this.chName(ch).toLowerCase().includes(f);
    const sect = (title, list) => list.length ? `<div class="chat-section">${title}</div>${list.map(item).join('')}` : '';
    let html = sect('Channels', sorted.filter(c => (c.kind === 'company' || c.kind === 'department') && match(c))) + sect('Groups', sorted.filter(c => c.kind === 'group' && match(c))) + sect('Direct messages', sorted.filter(c => c.kind === 'dm' && match(c)));
    if (f) {
      const have = new Set(this.channels.filter(c => c.kind === 'dm').map(c => c.peer));
      const more = this.people.filter(p => !have.has(p.id) && p.name.toLowerCase().includes(f));
      if (more.length) html += `<div class="chat-section">People</div>` + more.map(p => `<button class="chat-item" data-newdm="${esc(p.id)}">${avatar(p, { size: 42, online: this.online.has(p.id) })}<span class="meta"><span class="row1"><b>${esc(p.name)}</b></span><span class="row2"><span class="prev">${esc(p.department)} · start a conversation</span></span></span></button>`).join('');
    }
    return html || '<div class="empty">No conversations match.</div>';
  },
  renderList() { const el = $('#chat-list'); if (!el) return; el.innerHTML = this.listHtml(); paint(el); this.bindList(); },
  header() {
    const ch = this.channel(this.active);
    if (!ch) return { name: '', sub: '' };
    const typers = (this.typing[ch.id] || []).map(id => this.person(id).name.split(' ')[0]);
    let sub = ch.kind === 'dm' ? (this.isOnline(ch) ? 'Online now' : 'Offline') : ch.kind === 'group' ? (ch.members ? ch.members.length + ' people' : 'Group conversation') : ch.kind === 'company' ? 'Everyone at DigitalBurj' : 'Everyone in ' + ch.name;
    return { name: this.chName(ch), sub: typers.length ? `<span class="typing-line">${esc(typers.join(', '))} ${typers.length > 1 ? 'are' : 'is'} typing…</span>` : esc(sub), ch };
  },
  renderHeader() {
    const el = $('#chat-head'); const h = this.header(); if (!el || !h.ch) return;
    el.innerHTML = `<button class="icon-btn back" data-act="back" aria-label="Back to conversations">${ico('back')}</button>${chanAvatar(h.ch, 42, this.isOnline(h.ch))}<div class="who"><h2>${esc(h.name)}</h2><small>${h.sub}</small></div>`;
    paint(el); $('[data-act=back]', el).onclick = () => { this.view = 'list'; this.active = null; this.renderAll(); };
  },
  pinnedBar() {
    const pinned = (this.msgs[this.active] || []).filter(m => m.pinned && !m.deleted).pop();
    return pinned ? `<div class="pin-bar" data-goto="${esc(pinned.id)}">${ico('pin')}<span><b>Pinned</b> · ${esc(pinned.body || pinned.file?.name || '')}</span></div>` : '';
  },
  msgHtml(m, i, list, divider) {
    const own = m.sender === this.me, prev = list[i - 1], next = list[i + 1];
    const grp = (a, b) => a && b && a.sender === b.sender && !a.deleted === !b.deleted && sameDay(a.created, b.created) && new Date(b.created) - new Date(a.created) < 300000 && !(divider && divider === b.id);
    const first = !grp(prev, m), last = !grp(m, next);
    const fresh = this.rendered[this.active] && !this.rendered[this.active].has(m.id) && this.rendered[this.active].size > 0;
    const people = this.people;
    const ch = this.channel(this.active);
    let attach = '';
    if (m.file && !m.deleted) {
      attach = m.file.mime && m.file.mime.startsWith('image/') && !demo ? `<img class="attach-img" loading="lazy" alt="${esc(m.file.name)}" data-lightbox="${esc(m.file.id)}" src="${fileUrl(m.file.id, true)}">` : `<a class="attach-file" ${demo ? '' : `href="${fileUrl(m.file.id)}"`} download>${ftype(m.file.name, m.file.mime, 'sm')}<span><b>${esc(m.file.name)}</b><small>${bytes(m.file.size)}</small></span></a>`;
    }
    const reply = m.reply ? `<button class="reply-chip" data-goto="${esc(m.reply.id)}"><b>${esc(this.person(m.reply.sender).name)}</b><span>${m.reply.deleted ? 'Message deleted' : esc(m.reply.body || '📎 Attachment')}</span></button>` : '';
    const reacts = Object.entries(m.reactions || {}).map(([e, ids]) => `<button class="react ${ids.includes(this.me) ? 'mine' : ''} ${this.flashReact === e + m.id ? 'new' : ''}" data-react="${esc(e)}" data-mid="${esc(m.id)}">${e}<span>${ids.length}</span></button>`).join('');
    const moderate = ch && (ch.kind === 'company' || ch.kind === 'department') && (owner() || canAny('announcements.publish'));
    const tools = m.deleted || m.pending || m.failed ? '' : `<div class="msg-tools" role="toolbar" aria-label="Message actions"><button class="emo" data-react="👍" data-mid="${esc(m.id)}" aria-label="React thumbs up">👍</button><button class="emo" data-react="❤️" data-mid="${esc(m.id)}" aria-label="React heart">❤️</button><button class="emo" data-react="😂" data-mid="${esc(m.id)}" aria-label="React laugh">😂</button><button data-act="more-react" data-mid="${esc(m.id)}" aria-label="More reactions">${ico('smile', 'sm')}</button><button data-act="reply" data-mid="${esc(m.id)}" aria-label="Reply">${ico('reply', 'sm')}</button>${own ? `<button data-act="edit" data-mid="${esc(m.id)}" aria-label="Edit">${ico('edit', 'sm')}</button>` : ''}<button data-act="pin" data-mid="${esc(m.id)}" aria-label="Pin">${ico('pin', 'sm')}</button>${own || moderate ? `<button data-act="delete" data-mid="${esc(m.id)}" aria-label="Delete">${ico('trash', 'sm')}</button>` : ''}</div>`;
    let meta = '';
    if (m.failed) meta = `<span class="msg-meta">Not sent · <button class="retry" data-retry="${esc(m.id)}">Retry</button></span>`;
    else if (last) {
      let status = '';
      if (own) {
        const lastOwn = [...list].reverse().find(x => x.sender === this.me && !x.pending && !x.failed);
        const seen = ch && ch.peer_read && ch.peer_read >= m.created;
        status = m.pending ? ico('clock') : (lastOwn && lastOwn.id === m.id ? (seen ? `<span class="seen">${ico('checks')}Seen</span>` : `${ico('check')}Delivered`) : ico('check'));
      }
      meta = `<span class="msg-meta">${esc(new Date(m.created).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))}${m.edited && !m.deleted ? ' · edited' : ''}${m.pinned ? ' · pinned' : ''} ${status}</span>`;
    }
    const bubble = m.deleted ? '<div class="bubble deleted">This message was deleted</div>' : `<div class="bubble ${m.pending ? 'pending' : ''} ${m.failed ? 'failed' : ''}">${reply}${attach}${m.body ? richText(m.body, people) : ''}</div>`;
    const showName = !own && first && ch && ch.kind !== 'dm';
    return `${divider === m.id ? `<div class="new-sep" id="new-sep">New messages</div>` : ''}${first && (!prev || !sameDay(prev.created, m.created)) ? `<div class="day-sep">${esc(dayLabel(m.created))}</div>` : ''}<div class="msg ${own ? 'own' : ''} ${first ? 'first' : ''} ${last ? 'last' : ''} ${fresh ? 'fresh' : ''}" data-mid="${esc(m.id)}"><span class="av-slot">${!own && last ? avatar(this.person(m.sender), { size: 34, online: this.online.has(m.sender) }) : ''}</span><div class="msg-body">${showName ? `<div class="who-line">${esc(this.senderName(m))}</div>` : ''}${tools}${bubble}${reacts ? `<div class="reacts">${reacts}</div>` : ''}${meta}</div></div>`;
  },
  threadHtml() {
    const list = this.msgs[this.active] || [], ch = this.channel(this.active);
    if (!ch) return '';
    const from = this.unreadFrom[this.active];
    const divider = from !== undefined && from !== null ? (list.find(m => m.created > from && m.sender !== this.me && !m.deleted) || {}).id : null;
    if (!list.length) return `<div class="empty-chat">${chanAvatar(ch, 64)}<h3>${esc(this.chName(ch))}</h3><p>${ch.kind === 'dm' ? 'This is the start of your conversation. Say hello 👋' : 'No messages yet. Start the conversation.'}</p></div>`;
    const typers = (this.typing[ch.id] || []);
    const html = list.map((m, i) => this.msgHtml(m, i, list, divider)).join('');
    const typingHtml = typers.length ? `<div class="typing-bubble">${avatar(this.person(typers[0]), { size: 30 })}<span class="dots"><i></i><i></i><i></i></span></div>` : '';
    return (this.hasMore[this.active] ? '<div class="day-sep">Scroll up for earlier messages</div>' : '') + html + typingHtml;
  },
  renderThread(opt = {}) {
    const th = $('#thread'); if (!th) return;
    const nearBottom = th.scrollHeight - th.scrollTop - th.clientHeight < 140;
    const prevTop = th.scrollTop;
    th.innerHTML = this.threadHtml();
    paint(th);
    const pin = $('#pin-slot'); if (pin) pin.innerHTML = this.pinnedBar();
    this.bindThread();
    this.rendered[this.active] = new Set((this.msgs[this.active] || []).map(m => m.id));
    const sep = $('#new-sep');
    if (opt.toUnread && sep) { th.scrollTop = sep.offsetTop - 80; }
    else if (opt.stick || (!opt.keep && nearBottom) || opt.toUnread) { th.scrollTop = th.scrollHeight; }
    else th.scrollTop = prevTop;
    this.jumpState();
    if (this.flashReact) this.flashReact = null;
  },
  jumpState() {
    const th = $('#thread'), j = $('#jump'); if (!th || !j) return;
    const away = th.scrollHeight - th.scrollTop - th.clientHeight > 220;
    j.hidden = !away;
    const n = this.channel(this.active)?.unread || 0;
    $('.n', j).textContent = n; $('.n', j).hidden = !n;
  },
  renderComposerBars() {
    const rb = $('#reply-slot'), pf = $('#pending-files'); if (!rb) return;
    const target = this.reply || (this.editing && this.find(this.active, this.editing));
    rb.innerHTML = target ? `<div class="reply-bar"><div><b>${this.editing ? 'Editing message' : 'Replying to ' + esc(this.senderName(target))}</b><span>${esc(target.body || '📎 Attachment')}</span></div><button class="tool-btn" data-act="cancel-reply" aria-label="Cancel">${ico('close', 'sm')}</button></div>` : '';
    $('[data-act=cancel-reply]', rb)?.addEventListener('click', () => { this.reply = null; if (this.editing) { this.editing = null; $('#chat-input').value = this.drafts[this.active] || ''; this.autosize(); } this.renderComposerBars(); });
    pf.innerHTML = this.files.map((f, i) => `<div class="pfile">${ftype(f.name, f.mime, 'sm')}<b>${esc(f.name)}</b><button data-rmfile="${i}" aria-label="Remove ${esc(f.name)}">${ico('close', 'sm')}</button><span class="bar" data-p="${Math.round(f.progress)}"></span></div>`).join('');
    paint(pf);
    $$('[data-rmfile]', pf).forEach(b => b.onclick = () => { this.files.splice(+b.dataset.rmfile, 1); this.renderComposerBars(); });
    this.updateSend();
  },
  paintFiles() { $$('#pending-files .bar').forEach((el, i) => this.files[i] && el.style.setProperty('--p', Math.round(this.files[i].progress))); },
  updateSend() { const b = $('#chat-send'), ta = $('#chat-input'); if (b && ta) b.disabled = this.files.some(f => f.uploading) || !(ta.value.trim() || this.files.some(f => f.id)); },
  autosize() { const ta = $('#chat-input'); if (!ta) return; ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'; },

  skeleton() {
    return `<div class="chat-app" id="chat-app" data-view="${this.active ? this.view : 'list'}">
<aside class="chat-side"><div class="chat-side-head"><h2>Messages</h2><div class="toolbar-mini"><button class="icon-btn" data-act="new-chat" aria-label="New conversation" title="New conversation">${ico('plus')}</button></div></div><div class="chat-search">${ico('search', 'sm')}<input id="chat-filter" placeholder="Search people and channels" autocomplete="off" value="${esc(this.filter)}"></div><div class="chat-list" id="chat-list"></div></aside>
<section class="chat-main" id="chat-main">${this.active ? this.mainHtml() : `<div class="thread"><div class="empty-chat"><span class="av chan" data-size="64">${ico('messages')}</span><h3>Your conversations</h3><p>Choose a conversation or start a new one. Messages arrive instantly while you are here.</p></div></div>`}</section></div>`;
  },
  mainHtml() {
    return `<header class="chat-head" id="chat-head"></header><div id="pin-slot"></div><div class="thread" id="thread" aria-live="polite"></div>
<button class="jump" id="jump" hidden aria-label="Jump to latest message">${ico('arrowUp', 'sm')}<span>Latest</span><span class="n" hidden>0</span></button>
<div class="composer-wrap" id="composer"><div id="reply-slot"></div><div class="pending-files" id="pending-files"></div>
<div class="composer2"><button class="tool-btn" data-act="attach" aria-label="Attach files" title="Attach files">${ico('attach')}</button><input type="file" id="chat-file" multiple hidden>
<textarea id="chat-input" rows="1" maxlength="4000" placeholder="Write a message…  (Enter to send, Shift+Enter for a new line)" aria-label="Message"></textarea>
<button class="tool-btn" data-act="emoji" aria-label="Insert emoji" title="Emoji">${ico('smile')}</button><button class="send-btn" id="chat-send" disabled aria-label="Send message">${ico('send')}</button></div></div>
<div class="drop-veil" id="drop-veil" hidden>${ico('upload')}<div>Drop to attach<br><small>Files up to 20 MB</small></div></div>`;
  },
  renderAll() { const root = $('#chat-root'); if (!root) return; root.innerHTML = this.skeleton(); this.afterMount(); },
  afterMount() {
    paint($('#chat-app'));
    this.renderList();
    $('#chat-filter').oninput = e => { this.filter = e.target.value; this.renderList(); };
    $('[data-act=new-chat]').onclick = () => this.newChat();
    if (!this.active) return;
    this.renderHeader(); this.renderThread({ toUnread: true }); this.renderComposerBars();
    const ta = $('#chat-input'); ta.value = this.drafts[this.active] || ''; this.autosize(); this.updateSend();
    this.bindComposer();
  },

  /* ----- bindings ----- */
  bindList() {
    $$('[data-chat]').forEach(b => b.onclick = () => this.open(b.dataset.chat));
    $$('[data-newdm]').forEach(b => b.onclick = async () => { try { const r = await collab('chat/dm', { user_id: b.dataset.newdm }); await this.rebootstrap(); this.filter = ''; this.open(r.channel); } catch (e) { toast(e.message); } });
  },
  bindThread() {
    const th = $('#thread'); if (!th) return;
    th.onscroll = () => { this.jumpState(); if (th.scrollTop < 60) this.loadOlder(); if (th.scrollHeight - th.scrollTop - th.clientHeight < 60) this.maybeRead(200); };
    $$('[data-react]', th).forEach(b => b.onclick = e => { e.stopPropagation(); this.react(b.dataset.mid, b.dataset.react); });
    $$('[data-act]', th).forEach(b => b.onclick = e => { e.stopPropagation(); this.messageAction(b.dataset.act, b.dataset.mid, b); });
    $$('[data-retry]', th).forEach(b => b.onclick = () => this.retry(b.dataset.retry));
    $$('[data-goto]').forEach(b => b.onclick = () => this.goto(b.dataset.goto));
    $$('[data-lightbox]', th).forEach(img => img.onclick = () => this.lightbox(img.src));
    $$('.msg', th).forEach(el => { el.onclick = ev => { if (mq('(hover:none)') && !ev.target.closest('button,a,img')) { $$('.tools-open', th).forEach(x => x !== el && x.classList.remove('tools-open')); el.classList.toggle('tools-open'); } }; });
    const j = $('#jump'); if (j) j.onclick = () => { th.scrollTo ? th.scrollTo({ top: th.scrollHeight, behavior: 'smooth' }) : (th.scrollTop = th.scrollHeight); };
  },
  goto(id) { const el = $(`.msg[data-mid="${cssEsc(id)}"]`); if (!el) return toast('That message is further back in the conversation.'); el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 2400); },
  lightbox(src) { const lb = document.createElement('div'); lb.className = 'lightbox'; lb.innerHTML = `<img alt="Attachment preview" src="${esc(src)}">`; lb.onclick = () => lb.remove(); document.body.appendChild(lb); const k = e => { if (e.key === 'Escape') { lb.remove(); document.removeEventListener('keydown', k); } }; document.addEventListener('keydown', k); },
  messageAction(act, id, btn) {
    const m = this.find(this.active, id); if (!m) return;
    if (act === 'reply') { this.reply = m; this.editing = null; this.renderComposerBars(); $('#chat-input').focus(); }
    else if (act === 'edit') { this.editing = id; this.reply = null; this.renderComposerBars(); const ta = $('#chat-input'); this.drafts[this.active] = ta.value; ta.value = m.body; this.autosize(); this.updateSend(); ta.focus(); }
    else if (act === 'pin') collab('chat/pin', { id }).then(() => this.sync()).catch(e => toast(e.message));
    else if (act === 'delete') formDialog('Delete message', '<p>This removes the message for everyone in the conversation.</p>', async () => { await collab('chat/delete', { id }); m.deleted = 1; m.body = ''; this.renderThread({ keep: true }); }, 'Delete');
    else if (act === 'more-react') this.popReactions(id, btn);
  },
  popReactions(id) {
    this.closePop();
    const p = document.createElement('div'); p.className = 'pop emoji-grid'; p.id = 'pop';
    p.innerHTML = (this.emoji || []).map(e => `<button data-e="${e}">${e}</button>`).join('');
    $('#chat-main').appendChild(p);
    p.style.setProperty('bottom', '120px'); p.style.setProperty('right', '30px'); p.style.setProperty('left', 'auto');
    $$('button', p).forEach(b => b.onclick = () => { this.closePop(); this.react(id, b.dataset.e); });
    setTimeout(() => document.addEventListener('click', this.popClose = () => this.closePop(), { once: true }), 0);
  },
  closePop() { $('#pop')?.remove(); },
  bindComposer() {
    const ta = $('#chat-input'), main = $('#chat-main');
    ta.addEventListener('input', () => {
      this.drafts[this.active] = ta.value; this.autosize(); this.updateSend();
      if (!this.editing && ta.value.trim()) { this.typingChannel = this.active; this.typingUntil = Date.now() + 4000; }
      this.mentionCheck();
    });
    ta.addEventListener('keydown', e => {
      const pop = $('#pop.mention-pop');
      if (pop) {
        const items = $$('button', pop), cur = items.findIndex(b => b.classList.contains('sel'));
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); const n = (cur + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length; items.forEach((b, i) => b.classList.toggle('sel', i === n)); return; }
        if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); items[Math.max(cur, 0)].click(); return; }
        if (e.key === 'Escape') { this.closePop(); return; }
      }
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && !mq('(pointer:coarse)')) { e.preventDefault(); this.send(); }
      if (e.key === 'Escape' && (this.reply || this.editing)) { this.reply = null; this.editing = null; ta.value = this.drafts[this.active] || ''; this.autosize(); this.renderComposerBars(); }
      if (e.key === 'ArrowUp' && !ta.value) { const mine = [...(this.msgs[this.active] || [])].reverse().find(m => m.sender === this.me && !m.deleted && !m.pending); if (mine) this.messageAction('edit', mine.id); }
    });
    ta.addEventListener('paste', e => { const files = [...(e.clipboardData?.files || [])]; if (files.length) { e.preventDefault(); this.attach(files); } });
    $('#chat-send').onclick = () => this.send();
    $('[data-act=attach]').onclick = () => $('#chat-file').click();
    $('#chat-file').onchange = e => { this.attach([...e.target.files]); e.target.value = ''; };
    $('[data-act=emoji]').onclick = e => { e.stopPropagation(); this.closePop(); const p = document.createElement('div'); p.className = 'pop emoji-grid'; p.id = 'pop'; p.innerHTML = RICH_EMOJI.map(x => `<button data-e="${x}">${x}</button>`).join(''); $('#composer').appendChild(p); p.style.setProperty('left', 'auto'); p.style.setProperty('right', '18px'); $$('button', p).forEach(b => b.onclick = ev => { ev.stopPropagation(); const s = ta.selectionStart; ta.value = ta.value.slice(0, s) + b.dataset.e + ta.value.slice(ta.selectionEnd); ta.focus(); ta.selectionStart = ta.selectionEnd = s + b.dataset.e.length; ta.dispatchEvent(new Event('input')); }); setTimeout(() => document.addEventListener('click', () => this.closePop(), { once: true }), 0); };
    let depth = 0; const veil = $('#drop-veil');
    main.addEventListener('dragenter', e => { if ([...e.dataTransfer.types].includes('Files')) { depth++; veil.hidden = false; } });
    main.addEventListener('dragover', e => e.preventDefault());
    main.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) veil.hidden = true; });
    main.addEventListener('drop', e => { e.preventDefault(); depth = 0; veil.hidden = true; if (e.dataTransfer.files.length) this.attach([...e.dataTransfer.files]); });
    if (!mq('(pointer:coarse)')) ta.focus({ preventScroll: true });
  },
  mentionCheck() {
    const ta = $('#chat-input'), upto = ta.value.slice(0, ta.selectionStart), m = /(^|\s)@([\w .'-]{0,30})$/.exec(upto);
    this.closePop();
    if (!m) return;
    const ch = this.channel(this.active);
    let pool = this.people;
    if (ch.kind === 'dm') pool = this.people.filter(p => p.id === ch.peer);
    if (ch.kind === 'group' && ch.members) pool = this.people.filter(p => ch.members.includes(p.id));
    const q = m[2].toLowerCase(), hits = pool.filter(p => p.name.toLowerCase().includes(q)).slice(0, 6);
    if (!hits.length) return;
    const p = document.createElement('div'); p.className = 'pop mention-pop'; p.id = 'pop';
    p.innerHTML = hits.map((h, i) => `<button class="${i ? '' : 'sel'}" data-id="${esc(h.id)}">${avatar(h, { size: 28 })}<span>${esc(h.name)}<small class="block">${esc(h.department)}</small></span></button>`).join('');
    $('#composer').appendChild(p); paint(p);
    $$('button', p).forEach(b => b.onclick = e => { e.preventDefault(); const person = this.person(b.dataset.id), start = ta.selectionStart - m[2].length - 1; ta.value = ta.value.slice(0, start) + '@' + person.name + ' ' + ta.value.slice(ta.selectionStart); ta.focus(); const pos = start + person.name.length + 2; ta.selectionStart = ta.selectionEnd = pos; this.closePop(); ta.dispatchEvent(new Event('input')); });
  },
  newChat() {
    const people = this.people;
    formDialog('Start a conversation', `<label for="f-mode">Type</label><select id="f-mode" name="mode"><option value="dm">Direct message</option><option value="group">Group conversation</option></select><div id="grp-name" hidden><label for="f-gname">Group name</label><input id="f-gname" name="gname" maxlength="60"></div><label>People</label><div class="permission-matrix">${people.map(p => `<label class="permission-row"><span><input type="${'checkbox'}" name="pick" value="${esc(p.id)}"> ${esc(p.name)}</span><small>${esc(p.department)}</small></label>`).join('') || '<p class="muted">No one is available to message.</p>'}</div>`,
      async b => {
        const picked = $$('[name=pick]:checked').map(x => x.value);
        if (b.mode === 'dm') { if (picked.length !== 1) throw Error('Choose exactly one person for a direct message.'); const r = await collab('chat/dm', { user_id: picked[0] }); await this.rebootstrap(); setTimeout(() => this.open(r.channel), 50); return; }
        if (!b.gname || !picked.length) throw Error('Name the group and choose at least one person.');
        const r = await collab('chat/group', { name: b.gname, members: picked }); await this.rebootstrap(); setTimeout(() => this.open(r.channel), 50);
      }, 'Start');
    $('#f-mode').onchange = e => { $('#grp-name').hidden = e.target.value !== 'group'; };
  }
};

/* Messages page integration */
function messagesViewV2() {
  Chat.ensure().catch(e => toast(e.message));
  return title('Collaboration / Messages', 'Talk to your team.', 'Direct messages, department channels and groups — with files, reactions and replies.') + '<div id="chat-root">' + (Chat.booted ? Chat.skeleton() : `<div class="chat-app"><aside class="chat-side"><div class="chat-side-head"><h2>Messages</h2></div><div class="chat-list">${[1, 2, 3, 4, 5].map(() => '<div class="chat-item"><span class="skeleton chat-skel-av"></span><span class="meta"><span class="skeleton chat-skel-line"></span></span></div>').join('')}</div></aside><section class="chat-main"><div class="thread"><div class="empty-chat"><div class="skeleton chat-skel-hero"></div></div></div></section></div>`) + '</div>';
}
featureViews.messages = messagesViewV2;

const featureBindBeforeChat = featureBind;
featureBind = function () { featureBindBeforeChat(); if (page === 'messages' && Chat.booted) Chat.afterMount(); Chat.ensure && Chat.allowed() && Chat.ensure().catch(() => {}); };
