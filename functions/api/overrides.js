// GET  /api/overrides?slug=<slug>     → return saved overrides for a slug
// POST /api/overrides                  → save a single line override

export const onRequestPost = async (context) => {
  const { user } = context.data;
  if (!user || !user.email) return json({ error: 'unauthenticated' }, 401);

  let body;
  try { body = await context.request.json(); } catch(e){ return json({ error: 'invalid_json' }, 400); }
  const { slug, versionKey, source, lineId, value, description } = body || {};
  if (!slug || !versionKey || !source || lineId === undefined || value === undefined){
    return json({ error: 'missing_fields', need: ['slug','versionKey','source','lineId','value'] }, 400);
  }

  const role = await getUserRoleForSlug(context, user.email, slug);
  if (role !== 'admin' && role !== 'editor'){
    return json({ error: 'forbidden', detail: 'editor or admin role required' }, 403);
  }

  const env = context.env || {};
  const token  = env.GITHUB_TOKEN;
  const owner  = env.GITHUB_OWNER;
  const repo   = env.GITHUB_REPO;
  const branch = env.GITHUB_BRANCH || 'main';
  if (!token || !owner || !repo) return json({ error: 'server_misconfigured' }, 500);

  const safeVer = String(versionKey).replace(/[^A-Za-z0-9._+-]/g, '_');
  const overridePath = `overrides/${slug}__${safeVer}__${source}.json`;
  const now = new Date();
  const ym = now.toISOString().slice(0,7);
  const auditPath = `audit/${ym}.jsonl`;

  try {
    const existing = await ghGetFile({ token, owner, repo, branch, path: overridePath });
    let fileData = {};
    if (existing){
      try { fileData = JSON.parse(existing.content); } catch(e){ fileData = {}; }
    }
    const lines = fileData.lines || {};
    lines[lineId] = {
      lineId,
      value,
      description: description || '',
      status: 'saved',
      saved_by: user.email,
      saved_at: now.toISOString(),
      reviewed_by: null,
      reviewed_at: null,
    };
    fileData.lines = lines;
    fileData._last_updated = now.toISOString();
    fileData._last_updated_by = user.email;
    fileData.slug = slug;
    fileData.versionKey = versionKey;
    fileData.source = source;

    await ghPutFile({ token, owner, repo, branch,
      path: overridePath,
      sha: existing ? existing.sha : undefined,
      content: JSON.stringify(fileData, null, 2),
      message: `overrides: ${slug} line ${lineId} saved by ${user.email}`,
    });

    const auditEntry = JSON.stringify({
      kind: 'override_save',
      ts: now.toISOString(),
      user: user.email,
      slug, versionKey, source, lineId,
    });
    const existingAudit = await ghGetFile({ token, owner, repo, branch, path: auditPath });
    const newAudit = (existingAudit ? existingAudit.content + '\n' : '') + auditEntry;
    await ghPutFile({ token, owner, repo, branch,
      path: auditPath,
      sha: existingAudit ? existingAudit.sha : undefined,
      content: newAudit,
      message: `audit: override_save ${slug} by ${user.email}`,
    });

    return json({ ok: true, lineId, status: 'saved' });
  } catch(e){
    return json({ error: 'github_write_failed', detail: String(e && e.message || e) }, 500);
  }
};

export const onRequestGet = async (context) => {
  const { user } = context.data;
  if (!user || !user.email){
    return json({ error: 'unauthenticated' }, 401);
  }

  const url = new URL(context.request.url);
  const slug = url.searchParams.get('slug');
  if (!slug) return json({ error: 'missing_slug' }, 400);

  let access = {};
  try {
    const u = new URL(context.request.url);
    u.pathname = '/access.json';
    const r = await context.env.ASSETS.fetch(u.toString());
    if (r.ok) access = await r.json();
  } catch (e){}
  const entry = (access.users || {})[user.email.toLowerCase()] || (access.users || {})[user.email];
  const role = entry?.role || 'denied';
  if (role === 'denied' || !entry){
    return json({ error: 'forbidden', detail: 'no access granted' }, 403);
  }
  const allowed = entry.slugs;
  const canSee = allowed === '*' || (Array.isArray(allowed) && allowed.includes(slug));
  if (!canSee){
    return json({ error: 'forbidden', detail: 'no access to this slug' }, 403);
  }

  const env = context.env || {};
  const token  = env.GITHUB_TOKEN;
  const owner  = env.GITHUB_OWNER;
  const repo   = env.GITHUB_REPO;
  const branch = env.GITHUB_BRANCH || 'main';
  if (!token || !owner || !repo){
    return json({ error: 'server_misconfigured' }, 500);
  }

  try {
    const dirUrl = `https://api.github.com/repos/${owner}/${repo}/contents/overrides?ref=${encodeURIComponent(branch)}`;
    const dirRes = await fetch(dirUrl, { headers: ghHeaders(token) });
    if (dirRes.status === 404){
      return json({ slug, overrides: {} });
    }
    if (!dirRes.ok) throw new Error('GH list ' + dirRes.status);
    const items = await dirRes.json();
    const out = {};
    const matching = items.filter(it => it.name && it.name.startsWith(slug + '__') && it.name.endsWith('.json'));

    await Promise.all(matching.map(async item => {
      const fileRes = await fetch(item.url, { headers: ghHeaders(token) });
      if (!fileRes.ok) return;
      const fj = await fileRes.json();
      const raw = atob((fj.content || '').replace(/\n/g,''));
      let parsed; try { parsed = JSON.parse(raw); } catch(e){ return; }
      const key = item.name.replace(/^.*?__/,'').replace(/\.json$/,'');
      out[key] = parsed;
    }));

    return json({ slug, overrides: out });
  } catch (e){
    return json({ error: 'github_read_failed', detail: String(e && e.message || e) }, 500);
  }
};

function json(obj, status=200){
  return new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
}
function ghHeaders(token){
  return {
    'authorization': `Bearer ${token}`,
    'accept': 'application/vnd.github+json',
    'x-github-api-version': '2022-11-28',
    'user-agent': 'bva-member-care-dashboard'
  };
}
async function loadAccess(context){
  try {
    const u = new URL(context.request.url);
    u.pathname = '/access.json';
    const r = await context.env.ASSETS.fetch(u.toString());
    if (r.ok) return await r.json();
  } catch(e){}
  return { users: {} };
}
async function getUserRoleForSlug(context, email, slug){
  const access = await loadAccess(context);
  const entry = (access.users || {})[email.toLowerCase()] || (access.users || {})[email];
  if (!entry) return 'denied';
  const allowed = entry.slugs;
  if (allowed !== '*' && !(Array.isArray(allowed) && allowed.includes(slug))) return 'denied';
  return entry.role || 'viewer';
}
async function ghGetFile({ token, owner, repo, branch, path }){
  const url = `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}?ref=${encodeURIComponent(branch)}`;
  const res = await fetch(url, { headers: ghHeaders(token) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GH GET ${path} ${res.status}`);
  const j = await res.json();
  const content = atob((j.content || '').replace(/\n/g,''));
  return { sha: j.sha, content };
}
async function ghPutFile({ token, owner, repo, branch, path, content, message, sha }){
  const url = `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}`;
  const body = {
    message,
    content: btoa(unescape(encodeURIComponent(content))),
    branch,
  };
  if (sha) body.sha = sha;
  else {
    const existing = await ghGetFile({ token, owner, repo, branch, path });
    if (existing) body.sha = existing.sha;
  }
  const res = await fetch(url, {
    method: 'PUT',
    headers: { ...ghHeaders(token), 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok){
    const t = await res.text().catch(() => res.statusText);
    throw new Error(`GH PUT ${path} ${res.status}: ${t}`);
  }
  return await res.json();
}
