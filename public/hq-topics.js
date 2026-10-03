'use strict';
/* HQ Discussions, command palette (⌘K) and the motion layer shared by every page. */

/* ---------------------------------------------------------------------------------
   Discussions: threaded topics by audience, with categories, status and moderation
   --------------------------------------------------------------------------------- */
const Topics = {
  d: null, open: null, detail: null, cat: 'All', status: 'Open', error: '',
  async load() {
    try { this.d = await collab('topics'); this.error = ''; } catch (e) { this.d = null; this.error = e.message; }
    if (page === 'discussions') this.paint();
  },
  async openTopic(id) {
    this.open = id; this.detail = null; this.paint();
    try { this.detail = await collab('topic?id=' + encodeURIComponent(id)); } catch (e) { toast(e.message); this.open = null; }
    this.paint();
  },
  listHtml() {
    if (this.error) return `<div class="notice">${esc(this.error)}</div>`;
    if (!this.d) return panel('Discussions', [1, 2, 3].map(() => '<div class="topic"><div class="skeleton skel-topic"></div></div>').join(''));
    const cats = ['All', ...this.d.categories], stats = ['Open', 'Resolved', 'Closed', 'All'];
    const rows = this.d.topics.filter(t => (this.cat === 'All' || t.category === this.cat) && (this.status === 'All' || t.status === this.status));
    const chips = `<div class="chips">${cats.map(c => `<button class="chip ${this.cat === c ? 'acc' : ''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('')}<span class="grow"></span>${stats.map(s => `<button class="chip ${this.status === s ? 'acc' : 'dim'}" data-status="${s}">${s}</button>`).join('')}</div>`;
    const list = rows.map((t, i) => `<button class="topic" data-topic="${esc(t.id)}" data-i="${Math.min(i, 12)}">${avatar({ id: t.author, name: t.author_name }, { size: 42 })}<span class="grow-col"><h3>${t.pinned ? ico('pin', 'sm') + ' ' : ''}${esc(t.title)}</h3><p>${esc(t.body)}</p><span class="chips"><span class="chip">${esc(t.category)}</span><span class="chip dim">${esc(t.department === 'All' ? 'Company-wide' : t.department)}</span>${t.status !== 'Open' ? `<span class="chip ${t.status === 'Resolved' ? 'ok' : 'dim'}">${t.status}</span>` : ''}<small>${esc(t.author_name)} · ${esc(timeLabel(t.updated))}</small></span></span><span class="replies-count">${t.replies}<small>replies</small></span></button>`).join('');
    return chips + `<section class="panel">${list || empty('No discussions match. Start one to get your team talking.')}</section>`;
  },
  postHtml(p, first) {
    return `<article class="post">${avatar({ id: p.author, name: p.author_name }, { size: 42 })}<div class="body"><b>${esc(p.author_name)}</b> <small>${esc(new Date(p.created).toLocaleString())}</small>${first ? '' : ''}<p>${richText(p.body, Chat.people)}</p></div></article>`;
  },
  detailHtml() {
    if (!this.detail) return `<button class="small" data-back>${ico('back', 'sm')} All discussions</button><section class="panel"><div class="post"><div class="skeleton skel-topic"></div></div></section>`;
    const { topic: t, replies } = this.detail, open = t.status === 'Open';
    const mod = t.can_moderate, pin = owner() || canAny('announcements.publish');
    return `<button class="small" data-back>${ico('back', 'sm')} All discussions</button>
<section class="panel"><header class="panel-head"><div><div class="chips"><span class="chip">${esc(t.category)}</span><span class="chip dim">${esc(t.department === 'All' ? 'Company-wide' : t.department)}</span><span class="chip ${t.status === 'Resolved' ? 'ok' : t.status === 'Closed' ? 'dim' : 'acc'}">${t.status}</span></div><h2 class="topic-title">${esc(t.title)}</h2></div><div class="toolbar">${mod ? `<button data-status-set="${open ? 'Resolved' : 'Open'}">${open ? 'Mark resolved' : 'Reopen'}</button>${t.status !== 'Closed' ? '<button data-status-set="Closed">Close</button>' : ''}` : ''}${pin ? `<button data-pin>${t.pinned ? 'Unpin' : 'Pin'}</button>` : ''}</div></header>
${this.postHtml(t)}${replies.map(r => this.postHtml(r)).join('')}
${open ? `<form class="cmt-form" id="reply-form"><textarea name="body" required maxlength="8000" placeholder="Write a reply…" aria-label="Reply"></textarea><button class="primary" type="submit">Reply</button></form>` : '<div class="notice">This discussion is closed to new replies.</div>'}</section>`;
  },
  paint() {
    const root = $('#topics-root'); if (!root) return;
    root.innerHTML = this.open ? this.detailHtml() : this.listHtml();
    paint(root);
    $$('[data-cat]', root).forEach(b => b.onclick = () => { this.cat = b.dataset.cat; this.paint(); });
    $$('[data-status]', root).forEach(b => b.onclick = () => { this.status = b.dataset.status; this.paint(); });
    $$('[data-topic]', root).forEach(b => b.onclick = () => this.openTopic(b.dataset.topic));
    $('[data-back]', root)?.addEventListener('click', () => { this.open = null; this.detail = null; this.load(); this.paint(); });
    $$('[data-status-set]', root).forEach(b => b.onclick = async () => { try { await collab('topic-update', { id: this.open, status: b.dataset.statusSet }); await this.openTopic(this.open); } catch (e) { toast(e.message); } });
    $('[data-pin]', root)?.addEventListener('click', async () => { try { await collab('topic-update', { id: this.open, pinned: !this.detail.topic.pinned }); await this.openTopic(this.open); } catch (e) { toast(e.message); } });
    const form = $('#reply-form', root);
    if (form) form.onsubmit = async e => { e.preventDefault(); const body = form.body.value.trim(); if (!body) return; try { await collab('topic-reply', { id: this.open, body }); await this.openTopic(this.open); } catch (er) { toast(er.message); } };
  },
  create() {
    const audiences = ['All', ...scopeFor('tasks.view').concat(user.department).filter((v, i, a) => a.indexOf(v) === i)];
    formDialog('Start a discussion', `<label for="f-department">Audience</label><select id="f-department" name="department">${options(audiences, user.department)}</select><label for="f-category">Category</label><select id="f-category" name="category">${options(this.d?.categories || ['General', 'Decision', 'Question', 'Idea'])}</select>${field('title', 'Title')}${field('body', 'What would you like to discuss?', 'textarea')}`,
      async b => { const r = await collab('topic-create', b); this.open = null; setTimeout(() => this.openTopic(r.id), 50); }, 'Post discussion');
  }
};
function discussionsView() {
  Chat.allowed() && Chat.ensure().catch(() => {});
  return title('Workspace / Discussions', 'Decide together, in the open.', 'Longer conversations by audience — proposals, questions and decisions that should stay findable.', canAny('messages.use') ? `<button class="primary" data-action="new-topic">＋ New discussion</button>` : '') + '<div id="topics-root"></div>';
}
featureViews.discussions = discussionsView;
const featureActionBeforeTopics = featureAction;
featureAction = function (a) { if (a === 'new-topic') { Topics.create(); return true; } return featureActionBeforeTopics(a); };
const featureBindBeforeTopics = featureBind;
featureBind = function () { featureBindBeforeTopics(); if (page === 'discussions') { Topics.paint(); Topics.load(); } };

/* ---------------------------------------------------------------------------------
   Command palette
   --------------------------------------------------------------------------------- */
const Palette = {
  el: null, items: [], sel: 0, timer: null, q: '', seq: 0,
  base() {
    const nav = moduleNavigation().map(([id, label]) => ({ group: 'Go to', icon: id, title: label, sub: 'Open ' + label.toLowerCase(), run: () => goPage(id) }));
    const act = [];
    if (Chat.allowed()) act.push({ group: 'Actions', icon: 'messages', title: 'New message', sub: 'Start a direct or group conversation', run: () => { goPage('messages'); setTimeout(() => Chat.newChat(), 400); } });
    if (canAny('files.personal') || canAny('files.view')) act.push({ group: 'Actions', icon: 'files', title: 'Upload a document', sub: 'Open Documents', run: () => { goPage('files'); setTimeout(() => $('#docs-file')?.click(), 600); } });
    if (Chat.allowed()) act.push({ group: 'Actions', icon: 'discussions', title: 'Start a discussion', sub: 'Open a topic for your team', run: () => { goPage('discussions'); setTimeout(() => Topics.create(), 400); } });
    act.push({ group: 'Actions', icon: 'settings', title: motionOff() ? 'Turn motion on' : 'Pause motion', sub: 'Animations and effects', run: () => setMotion(!motionOff()) });
    return [...act, ...nav];
  },
  openUI() {
    if (this.el) return;
    const veil = document.createElement('div'); veil.className = 'palette-veil';
    veil.innerHTML = `<div class="palette" role="dialog" aria-label="Search and commands"><div class="palette-input">${ico('search')}<input id="pal-q" placeholder="Search people, documents, messages, discussions… or type a command" autocomplete="off" aria-label="Search"></div><div class="palette-list" id="pal-list"></div><div class="palette-foot"><span><kbd>↑</kbd><kbd>↓</kbd>navigate</span><span><kbd>Enter</kbd>open</span><span><kbd>Esc</kbd>close</span></div></div>`;
    document.body.appendChild(veil); this.el = veil;
    veil.onclick = e => { if (e.target === veil) this.close(); };
    const input = $('#pal-q', veil); input.focus();
    input.oninput = () => { this.q = input.value.trim(); clearTimeout(this.timer); this.timer = setTimeout(() => this.search(), 180); this.render(this.localMatches()); };
    input.onkeydown = e => {
      if (e.key === 'Escape') this.close();
      else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); this.sel = (this.sel + (e.key === 'ArrowDown' ? 1 : -1) + this.items.length) % Math.max(this.items.length, 1); this.mark(); }
      else if (e.key === 'Enter') { e.preventDefault(); this.items[this.sel]?.run(), this.close(); }
    };
    this.render(this.base());
  },
  close() { this.el?.remove(); this.el = null; this.q = ''; },
  localMatches() { const q = this.q.toLowerCase(); return q ? this.base().filter(i => (i.title + ' ' + i.sub).toLowerCase().includes(q)) : this.base(); },
  async search() {
    const n = ++this.seq, q = this.q;
    if (q.length < 2) return;
    try {
      const d = await collab('search?q=' + encodeURIComponent(q));
      if (n !== this.seq || !this.el) return;
      const icons = { Person: 'staff', Job: 'tasks', Document: 'files', Discussion: 'discussions', Message: 'messages' };
      const found = d.results.map(r => ({ group: r.type + (r.type.endsWith('s') ? '' : 's'), icon: icons[r.type] || 'overview', title: r.title, sub: r.subtitle, run: () => this.openResult(r) }));
      this.render([...this.localMatches(), ...found]);
    } catch { /* local matches stay */ }
  },
  openResult(r) {
    if (r.type === 'Message') { goPage('messages'); Chat.ensure().then(() => Chat.open(r.channel)); }
    else if (r.type === 'Document') { Files.tab = r.scope || 'personal'; Files.dept = r.department || ''; Files.folder = ''; Files.d = null; goPage('files'); setTimeout(() => Files.drawer(r.id), 350); }
    else if (r.type === 'Discussion') { goPage('discussions'); setTimeout(() => Topics.openTopic(r.id), 250); }
    else if (r.type === 'Person') { const dm = Chat.allowed() && Chat.people.find(p => p.id === r.id); if (dm) { goPage('messages'); collab('chat/dm', { user_id: r.id }).then(async x => { await Chat.rebootstrap(); Chat.open(x.channel); }).catch(e => toast(e.message)); } else goPage('staff'); }
    else goPage(r.page || 'overview');
  },
  render(items) {
    this.items = items.slice(0, 40); this.sel = 0;
    const list = $('#pal-list'); if (!list) return;
    let last = '';
    list.innerHTML = this.items.map((it, i) => `${it.group !== last ? `<div class="palette-group">${esc(last = it.group)}</div>` : ''}<button class="palette-item ${i === 0 ? 'sel' : ''}" data-idx="${i}"><span class="tile">${ico(it.icon, 'sm')}</span><span><b>${esc(it.title)}</b><small>${esc(it.sub || '')}</small></span></button>`).join('') || '<div class="empty">Nothing found.</div>';
    $$('.palette-item', list).forEach(b => { b.onclick = () => { this.items[+b.dataset.idx].run(); this.close(); }; b.onmousemove = () => { this.sel = +b.dataset.idx; this.mark(); }; });
  },
  mark() { $$('.palette-item').forEach((b, i) => { b.classList.toggle('sel', i === this.sel); if (i === this.sel) b.scrollIntoView({ block: 'nearest' }); }); }
};
function goPage(id) { page = id; query = ''; render(); window.scrollTo({ top: 0 }); }
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k' && user) { e.preventDefault(); Palette.el ? Palette.close() : Palette.openUI(); }
});

/* ---------------------------------------------------------------------------------
   Motion layer: entrances, counters, spotlight, nav indicator, pause control
   --------------------------------------------------------------------------------- */
const motionOff = () => document.documentElement.classList.contains('motion-off');
function setMotion(off) {
  document.documentElement.classList.toggle('motion-off', off);
  try { localStorage.setItem('hq-motion', off ? 'off' : 'on'); } catch { /* private mode */ }
  $$('[data-act=motion]').forEach(b => { b.innerHTML = `${ico(off ? 'play' : 'pause', 'sm')} ${off ? 'Play motion' : 'Pause motion'}`; });
}
try { if (localStorage.getItem('hq-motion') === 'off' || mq('(prefers-reduced-motion:reduce)')) document.documentElement.classList.add('motion-off'); } catch { /* storage unavailable */ }
if (mq('(display-mode:standalone)') || navigator.standalone) document.documentElement.classList.add('pwa-standalone');

function countUp(el) {
  const target = Number(el.dataset.count); if (!Number.isFinite(target)) return;
  if (motionOff() || target === 0) { el.textContent = el.dataset.count; return; }
  const t0 = performance.now(), dur = 900;
  const step = t => { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3); el.textContent = Math.round(target * e); if (k < 1) raf(step); };
  el.textContent = '0'; raf(step);
}
function placeIndicator() {
  const nav = $('.sidebar .nav'), ind = $('.nav-indicator'), act = $('.sidebar .nav button.active');
  if (!nav || !ind) return;
  if (!act) { ind.style.setProperty('--o', 0); return; }
  ind.style.setProperty('--y', act.offsetTop + 'px'); ind.style.setProperty('--o', 1);
}
function motionAfterRender(entering) {
  const main = $('.main');
  if (main) {
    if (entering) {
      main.classList.add('enter');
      [...main.children].forEach((c, i) => c.style.setProperty('--i', Math.min(i, 9)));
      $$('[data-count]', main).forEach(countUp);
      setTimeout(() => main.classList.remove('enter'), 1400);
    } else $$('[data-count]', main).forEach(el => { el.textContent = el.dataset.count; });
    main.onpointermove = e => { const t = e.target.closest?.('.spot'); if (t) { const r = t.getBoundingClientRect(); t.style.setProperty('--mx', e.clientX - r.left + 'px'); t.style.setProperty('--my', e.clientY - r.top + 'px'); } };
  }
  paint();
  placeIndicator();
  raf(placeIndicator);
  $$('[data-act=motion]').forEach(b => { b.onclick = () => setMotion(!motionOff()); b.innerHTML = `${ico(motionOff() ? 'play' : 'pause', 'sm')} ${motionOff() ? 'Play motion' : 'Pause motion'}`; });
  $$('[data-act=palette]').forEach(b => b.onclick = () => Palette.openUI());
  if (typeof Chat !== 'undefined') Chat.updateBadges();
}
window.addEventListener('resize', () => placeIndicator());

/* ---------------------------------------------------------------------------------
   PWA: installable app shell with an offline fallback (API calls are never cached)
   --------------------------------------------------------------------------------- */
let installPrompt = null;
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installPrompt = e; $$('[data-act=install]').forEach(b => { b.hidden = false; }); });
window.addEventListener('appinstalled', () => { installPrompt = null; $$('[data-act=install]').forEach(b => { b.hidden = true; }); toast('HQ is installed on this device.'); });
function installApp() { if (installPrompt) { installPrompt.prompt(); installPrompt = null; } }

/* Native shells (the Android app) call this for the system back button. Returns true when HQ handled it. */
window.hqBack = () => {
  const dlg = document.querySelector('dialog[open]');
  if (dlg) { dlg.close(); return true; }
  if (typeof Files !== 'undefined' && document.querySelector('.drawer')) { Files.closeDrawer(); return true; }
  if (typeof Chat !== 'undefined' && page === 'messages' && Chat.active) { $('[data-act=back]')?.click(); return true; }
  if (page === 'discussions' && $('[data-back]')) { $('[data-back]').click(); return true; }
  if (user && page !== 'overview') { goPage('overview'); return true; }
  return false;
};
