'use strict';
/* HQ Documents: personal vault, department and company libraries, shared-with-me, trash, preview + discussion drawer. */

const Files = {
  tab: '', dept: '', folder: '', trash: false, q: '', mode: 'grid', d: null, loading: false, uploads: [], error: '', seq: 0,

  tabs() {
    const t = [];
    if (canAny('files.personal')) t.push(['personal', 'My vault', 'lock']);
    if (scopeFor('files.view').length) t.push(['department', 'Department', 'departments']);
    if (canAny('files.view')) t.push(['company', 'Company', 'files']);
    if (canAny('files.personal')) t.push(['shared', 'Shared with me', 'share']);
    return t;
  },
  depts() { return scopeFor('files.view'); },
  begin() {
    const tabs = this.tabs();
    if (!tabs.some(t => t[0] === this.tab)) { this.tab = tabs[0]?.[0] || ''; this.folder = ''; this.trash = false; }
    if (this.tab === 'department' && !this.depts().includes(this.dept)) this.dept = this.depts().includes(user.department) ? user.department : this.depts()[0] || '';
  },
  query() {
    const q = new URLSearchParams({ scope: this.tab });
    if (this.tab === 'department') q.set('department', this.dept);
    if (this.folder) q.set('folder', this.folder);
    if (this.trash) q.set('trash', '1');
    if (this.q) q.set('q', this.q);
    return q.toString();
  },
  async load(quiet) {
    if (!this.tab) { this.d = null; this.paint(); return; }
    const n = ++this.seq;
    if (!quiet) { this.loading = true; this.paint(); }
    try { const d = await collab('files?' + this.query()); if (n !== this.seq) return; this.d = d; this.error = ''; }
    catch (e) { if (n !== this.seq) return; this.d = null; this.error = e.message; }
    this.loading = false; this.paint();
  },
  go(patch) { Object.assign(this, patch); this.load(); },

  tabsHtml() {
    return `<div class="docs-tabs" id="docs-tabs"><span class="slider"></span>${this.tabs().map(([k, l, i]) => `<button data-tab="${k}" class="${this.tab === k ? 'active' : ''}">${ico(i, 'sm')}${l}</button>`).join('')}</div>`;
  },
  paintTabs() {
    const bar = $('#docs-tabs'); if (!bar) return;
    const act = $('button.active', bar), s = $('.slider', bar);
    if (act && s) { s.style.setProperty('--x', act.offsetLeft - 5 + 'px'); s.style.setProperty('--w', act.offsetWidth + 'px'); }
  },
  cardHtml(f, i) {
    return `<button class="fcard" data-file="${esc(f.id)}" data-i="${Math.min(i, 14)}">${f.pinned ? `<span class="pinned">${ico('pin')}</span>` : ''}<div class="top">${ftype(f.name, f.mime)}</div><h3>${esc(f.name)}</h3><small>${bytes(f.size)} · ${esc(timeLabel(f.updated))}${f.comments ? ` · ${f.comments} comment${f.comments > 1 ? 's' : ''}` : ''}</small></button>`;
  },
  rowHtml(f, i) {
    return `<button class="frow" data-file="${esc(f.id)}" data-i="${Math.min(i, 20)}">${ftype(f.name, f.mime, 'sm')}<span class="nm"><b>${esc(f.name)}${f.pinned ? ' 📌' : ''}</b><small>${esc(f.description || (f.comments ? f.comments + ' comments' : ''))}</small></span><span class="col">${esc(f.owner_name)}</span><span class="col">${bytes(f.size)}</span><span class="col">${esc(timeLabel(f.updated))}</span></button>`;
  },
  folderHtml(fo, i) {
    return `<button class="fcard folder-card" data-folder="${esc(fo.id)}" data-i="${Math.min(i, 14)}"><span class="fi">${ico('folder', 'lg')}</span><span><h3>${esc(fo.name)}</h3><small>Folder</small></span></button>`;
  },
  html() {
    const d = this.d, tabs = this.tabs();
    if (!tabs.length) return `<div class="notice">Document libraries have not been assigned to your account. Ask the HQ owner to enable <strong>Use a private personal document vault</strong> or <strong>Read department and company documents</strong>.</div>`;
    const crumbs = d && !d.trash && d.scope !== 'shared' ? `<div class="crumbs"><button data-crumb="">${this.tab === 'personal' ? 'My vault' : this.tab === 'company' ? 'Company library' : esc(this.dept) + ' library'}</button>${d.breadcrumb.map(b => `<span class="sep">/</span><button data-crumb="${esc(b.id)}">${esc(b.name)}</button>`).join('')}</div>` : `<div class="crumbs"><b>${this.trash ? 'Trash · items are removed after ' + (d?.trash_days || 30) + ' days' : this.tab === 'shared' ? 'Shared with me' : ''}</b></div>`;
    const deptSel = this.tab === 'department' && this.depts().length > 1 ? `<select id="docs-dept" aria-label="Department library">${options(this.depts(), this.dept)}</select>` : '';
    const upload = d && d.can_upload && !this.trash ? `<button class="primary" data-act="upload">${ico('upload', 'sm')} Upload</button><button data-act="new-folder">${ico('folderPlus', 'sm')} New folder</button>` : '';
    const trashBtn = d && d.can_manage && this.tab !== 'shared' ? `<button data-act="trash" class="${this.trash ? 'primary' : ''}">${ico('trash', 'sm')} ${this.trash ? 'Back to files' : 'Trash'}</button>` : '';
    let body = '';
    if (this.loading && !d) body = `<div class="fgrid">${[1, 2, 3, 4, 5, 6].map(() => '<div class="fcard"><div class="skeleton skel-file-a"></div><div class="skeleton skel-file-b"></div></div>').join('')}</div>`;
    else if (this.error) body = `<div class="notice">${esc(this.error)}</div>`;
    else if (d) {
      const fol = d.folders.map((fo, i) => this.folderHtml(fo, i)).join('');
      body = !d.folders.length && !d.files.length ? `<div class="empty">${ico('folder', 'xl')}<br>${this.trash ? 'Trash is empty.' : this.q ? 'No documents match your search.' : d.can_upload ? 'This library is empty. Drag files here or choose <strong>Upload</strong>.' : 'No documents have been shared here yet.'}</div>`
        : (fol ? `<div class="fgrid fgrid-folders">${fol}</div>` : '') + (this.mode === 'grid' ? `<div class="fgrid">${d.files.map((f, i) => this.cardHtml(f, i + d.folders.length)).join('')}</div>` : `<div class="frows">${d.files.map((f, i) => this.rowHtml(f, i)).join('')}</div>`);
    }
    const quota = d && d.quota ? `<div class="quota-box"><small>${bytes(d.quota.used)} of ${bytes(d.quota.limit)} used</small><div class="quota" data-p="${Math.min(100, Math.round(d.quota.used / d.quota.limit * 100))}"><i></i></div></div>` : '';
    const dz = d && d.can_upload && !this.trash ? `<div class="dropzone" id="dropzone">${ico('upload')}<div><b>Drop files here</b> or <button class="small" data-act="upload">browse</button><br><small>Documents, images, archives, audio and video · up to 20 MB each · scanned for type integrity</small></div></div>` : '';
    const ups = this.uploads.length ? `<div class="upload-list">${this.uploads.map(u => `<div class="uprow">${ftype(u.name, u.mime, 'sm')}<span class="nm"><b>${esc(u.name)}</b><small class="${u.error ? 'err' : ''}">${u.error ? esc(u.error) : u.done ? 'Uploaded' : Math.round(u.progress) + '% · ' + bytes(u.size)}</small></span>${u.error ? `<button class="small" data-dismiss="${u.key}">Dismiss</button>` : u.done ? ico('check') : ''}<span class="bar" data-p="${Math.round(u.progress)}"></span></div>`).join('')}</div>` : '';
    return `${this.tabsHtml()}<div class="docs-bar">${crumbs}<span class="grow"></span>${deptSel}<div class="docs-search">${ico('search', 'sm')}<input id="docs-q" placeholder="Search this library" value="${esc(this.q)}"></div><div class="seg"><button data-mode="grid" class="${this.mode === 'grid' ? 'on' : ''}" aria-label="Grid view">${ico('grid', 'sm')}</button><button data-mode="list" class="${this.mode === 'list' ? 'on' : ''}" aria-label="List view">${ico('list', 'sm')}</button></div>${trashBtn}${upload}</div>${quota}${dz}${ups}${body}<input type="file" id="docs-file" multiple hidden>`;
  },
  paint() {
    const root = $('#files-root'); if (!root) return;
    root.innerHTML = this.html();
    paint(root);
    this.paintTabs();
    this.bind(root);
  },
  bind(root) {
    $$('[data-tab]', root).forEach(b => b.onclick = () => this.go({ tab: b.dataset.tab, folder: '', trash: false, q: '', d: null }));
    $$('[data-folder]', root).forEach(b => b.onclick = () => this.go({ folder: b.dataset.folder, q: '', d: null }));
    $$('[data-crumb]', root).forEach(b => b.onclick = () => this.go({ folder: b.dataset.crumb, d: null }));
    $$('[data-file]', root).forEach(b => b.onclick = () => (this.trash ? this.trashItem(b.dataset.file) : this.drawer(b.dataset.file)));
    $$('[data-mode]', root).forEach(b => b.onclick = () => { this.mode = b.dataset.mode; this.paint(); });
    $$('[data-act=upload]', root).forEach(b => b.onclick = () => $('#docs-file').click());
    $('[data-act=new-folder]', root)?.addEventListener('click', () => this.newFolder());
    $('[data-act=trash]', root)?.addEventListener('click', () => this.go({ trash: !this.trash, folder: '', q: '', d: null }));
    $('#docs-dept', root)?.addEventListener('change', e => this.go({ dept: e.target.value, folder: '', d: null }));
    $$('[data-dismiss]', root).forEach(b => b.onclick = () => { this.uploads = this.uploads.filter(u => String(u.key) !== b.dataset.dismiss); this.paint(); });
    const q = $('#docs-q', root);
    if (q) q.onkeydown = e => { if (e.key === 'Enter') this.go({ q: q.value.trim(), d: null }); }, q.onsearch = () => { if (!q.value && this.q) this.go({ q: '', d: null }); };
    const input = $('#docs-file', root); input.onchange = e => { this.upload([...e.target.files]); e.target.value = ''; };
    const dz = $('#dropzone', root);
    if (dz) {
      ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('over'); }));
      ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('over'); }));
      dz.addEventListener('drop', e => this.upload([...e.dataTransfer.files]));
    }
  },
  async upload(list) {
    if (!this.d?.can_upload) return;
    const params = { scope: this.tab }; if (this.tab === 'department') params.department = this.dept; if (this.folder) params.folder = this.folder;
    for (const file of list) {
      const rec = { key: Math.random(), name: file.name, size: file.size, mime: file.type, progress: 0 };
      if (file.size > 20 * 1048576) { rec.error = 'Larger than the 20 MB limit.'; this.uploads.push(rec); continue; }
      this.uploads.push(rec);
      uploadFile(file, params, p => { rec.progress = p; $$('.uprow .bar').forEach((el, i) => this.uploads[i] && el.style.setProperty('--p', Math.round(this.uploads[i].progress))); })
        .then(() => { rec.done = true; rec.progress = 100; this.load(true); setTimeout(() => { this.uploads = this.uploads.filter(u => u !== rec); this.paint(); }, 2500); })
        .catch(e => { rec.error = e.message; this.paint(); });
    }
    this.paint();
  },
  trashItem(id) {
    const f = this.d.files.find(x => x.id === id); if (!f) return;
    formDialog('Deleted document', `<p><strong>${esc(f.name)}</strong> · ${bytes(f.size)}</p><label class="permission-row"><span><input type="radio" name="choice" value="restore" checked> Restore to its library</span></label><label class="permission-row"><span><input type="radio" name="choice" value="purge"> Delete forever (cannot be undone)</span></label>`,
      async b => { await collab(b.choice === 'purge' ? 'files/purge' : 'files/restore', { id }); await this.load(true); }, 'Apply');
  },
  newFolder() {
    formDialog('New folder', field('name', 'Folder name'), async b => { await collab('files/folder', { scope: this.tab, department: this.dept, parent_id: this.folder || null, name: b.name }); await this.load(true); }, 'Create folder');
  },

  async drawer(id) {
    this.closeDrawer();
    const veil = document.createElement('div'); veil.className = 'drawer-veil';
    const dr = document.createElement('aside'); dr.className = 'drawer'; dr.setAttribute('role', 'dialog'); dr.setAttribute('aria-label', 'Document details');
    dr.innerHTML = `<div class="drawer-head"><h2>Loading…</h2><button class="icon-btn" data-close aria-label="Close">${ico('close')}</button></div><div class="drawer-body"><div class="skeleton skel-drawer"></div></div>`;
    document.body.append(veil, dr);
    const close = () => this.closeDrawer(); veil.onclick = close; $('[data-close]', dr).onclick = close;
    this.escHandler = e => { if (e.key === 'Escape') close(); }; document.addEventListener('keydown', this.escHandler);
    try { this.fill(dr, await collab('files/detail?id=' + encodeURIComponent(id))); }
    catch (e) { $('.drawer-body', dr).innerHTML = `<div class="notice">${esc(e.message)}</div>`; }
  },
  closeDrawer() { $$('.drawer,.drawer-veil').forEach(x => x.remove()); if (this.escHandler) document.removeEventListener('keydown', this.escHandler); },
  fill(dr, det) {
    const f = det.file, can = det.can_edit;
    const preview = demo ? `<div class="preview-box">${ftype(f.name, f.mime)}</div>` : f.mime.startsWith('image/') ? `<div class="preview-box"><img alt="${esc(f.name)}" src="${fileUrl(f.id, true)}"></div>` : f.mime === 'application/pdf' ? `<div class="preview-box"><iframe title="${esc(f.name)}" src="${fileUrl(f.id, true)}"></iframe></div>` : `<div class="preview-box">${ftype(f.name, f.mime)}</div>`;
    const lib = f.scope === 'personal' ? 'Personal vault' : f.scope === 'company' ? 'Company library' : f.department + ' library';
    dr.innerHTML = `<div class="drawer-head">${ftype(f.name, f.mime, 'sm')}<h2>${esc(f.name)}</h2><button class="icon-btn" data-close aria-label="Close">${ico('close')}</button></div>
<div class="drawer-body">${preview}
<div class="drawer-actions">${demo ? '' : `<a class="button primary" href="${fileUrl(f.id)}" download>${ico('download', 'sm')} Download</a>`}${can && !f.deleted_at ? `<button data-do="rename">${ico('edit', 'sm')} Rename</button><button data-do="pin">${ico('pin', 'sm')} ${f.pinned ? 'Unpin' : 'Pin'}</button><button data-do="move">${ico('folder', 'sm')} Move</button>` : ''}${f.scope === 'personal' && f.owner === user.id ? `<button data-do="share">${ico('share', 'sm')} Share</button>` : ''}${can ? `<button class="danger" data-do="delete">${ico('trash', 'sm')} Delete</button>` : ''}</div>
<dl class="kv"><dt>Library</dt><dd>${esc(lib)}</dd><dt>Owner</dt><dd>${esc(f.owner_name)}</dd><dt>Size</dt><dd>${bytes(f.size)}</dd><dt>Updated</dt><dd>${esc(new Date(f.updated).toLocaleString())}</dd>${f.description ? `<dt>Notes</dt><dd>${esc(f.description)}</dd>` : ''}${det.shared_with.length ? `<dt>Shared with</dt><dd>${det.shared_with.map(id => esc(Chat.person(id).name)).join(', ')}</dd>` : ''}</dl>
<h3>Discussion</h3><div id="cmts">${det.comments.map(c => `<div class="cmt">${avatar({ id: c.author, name: c.author_name }, { size: 32 })}<div><b>${esc(c.author_name)}</b> <small>${esc(timeLabel(c.created))}</small><p>${esc(c.body)}</p></div></div>`).join('') || '<p class="muted">No comments yet. Start the conversation about this document.</p>'}</div></div>
<form class="cmt-form" id="cmt-form"><textarea name="body" required maxlength="2000" placeholder="Add a comment…" aria-label="Comment"></textarea><button class="primary" type="submit">Post</button></form>`;
    paint(dr);
    const reopen = () => this.drawer(f.id);
    $('[data-close]', dr).onclick = () => this.closeDrawer();
    $('#cmt-form', dr).onsubmit = async e => { e.preventDefault(); const body = e.target.body.value.trim(); if (!body) return; try { await collab('files/comment', { id: f.id, body }); this.fill(dr, await collab('files/detail?id=' + encodeURIComponent(f.id))); this.load(true); } catch (er) { toast(er.message); } };
    $$('[data-do]', dr).forEach(b => b.onclick = () => this.act(b.dataset.do, f, det, reopen));
  },
  act(a, f, det, reopen) {
    if (a === 'rename') {
      formDialog('Rename document', field('name', 'File name') + field('description', 'Notes', 'textarea', false), async b => { await collab('files/update', { id: f.id, name: b.name, description: b.description }); await this.load(true); reopen(); });
      $('#f-name').value = f.name; $('#f-description').value = f.description || '';
      return;
    }
    if (a === 'pin') return collab('files/update', { id: f.id, pinned: !f.pinned }).then(() => { this.load(true); reopen(); }).catch(e => toast(e.message));
    if (a === 'delete') return formDialog('Move to trash', `<p><strong>${esc(f.name)}</strong> will be moved to the trash and removed permanently after 30 days.</p>`, async () => { await collab('files/delete', { id: f.id }); this.closeDrawer(); await this.load(true); }, 'Move to trash');
    if (a === 'move') {
      const opts = [['', 'Library root'], ...(this.d?.breadcrumb || []).map(b => [b.id, b.name]), ...(this.d?.folders || []).map(x => [x.id, x.name])];
      return formDialog('Move document', `<label for="f-folder">Destination</label><select id="f-folder" name="folder">${opts.map(([v, l]) => `<option value="${esc(v)}" ${v === (f.folder_id || '') ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`, async b => { await collab('files/update', { id: f.id, folder_id: b.folder || null }); this.closeDrawer(); await this.load(true); }, 'Move');
    }
    if (a === 'share') return formDialog('Share privately', `<p>Recipients get read-only access. Remove everyone to stop sharing.</p><div class="permission-matrix">${Chat.people.map(p => `<label class="permission-row"><span><input type="checkbox" name="pick" value="${esc(p.id)}" ${det.shared_with.includes(p.id) ? 'checked' : ''}> ${esc(p.name)}</span><small>${esc(p.department)}</small></label>`).join('') || '<p class="muted">No one is available to share with.</p>'}</div>`, async () => { await collab('files/share', { id: f.id, user_ids: $$('[name=pick]:checked').map(x => x.value) }); reopen(); }, 'Update sharing');
  }
};

function filesView() {
  Files.begin();
  Chat.allowed() && Chat.ensure().catch(() => {});
  return title('Workspace / Documents', 'Everything your team knows, in one place.', 'A private vault, department libraries and a company library — with previews, comments and a 30-day trash.') + `<div id="files-root"></div>`;
}
featureViews.files = filesView;
const featureBindBeforeFiles = featureBind;
featureBind = function () { featureBindBeforeFiles(); if (page === 'files') { Files.paint(); Files.load(!!Files.d); } };
