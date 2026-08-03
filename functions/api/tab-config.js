// GET  /api/tab-config — return data/tab_visibility.json (admins only)
// POST /api/tab-config — replace it (admins only). Body: { hidden: ["<tab slug>", ...] }
//
// Mirrors /api/version-config: gated on the Cloudflare Access identity in context.data.user,
// commits to GitHub via GITHUB_TOKEN/OWNER/REPO env vars, then Cloudflare Pages rebuilds so
// data/tab_visibility.json (read directly by the dashboard) picks up the change.

export const onRequestGet = async (context) => {
  const { user } = context.data || {};
  if (!user || !user.email) return json({ error: 'unauthenticated' }, 401);
  if (!(await isAdmin(context, user))) return json({ error: 'forbidden', detail: 'admin role required' }, 403);
  return json(await loadConfig(context));
};

export const onRequestPost = async (context) => {
  const { user } = context.data || {};
  if (!user || !user.email) return json({ error: 'unauthenticated' }, 401);
  if (!(await isAdmin(context, user))) return json({ error: 'forbidden', detail: 'admin role required' }, 403);

  let body;
  try { body = await context.request.json(); } catch(e){ return json({ error: 'invalid_json' }, 400); }
  const hidden = Array.isArray(body && body.hidden) ? body.hidden.filter(x => typeof x === 'string') : [];

  const env = context.env || {};
  const token = env.GITHUB_TOKEN, owner = env.GITHUB_OWNER, repo = env.GITHUB_REPO, branch = env.GITHUB_BRANCH || 'main';
  if (!token || !owner || !repo) return json({ error: 'server_misconfigured' }, 500);

  const payload = JSON.stringify({
    _comment: 'Sidebar tab slugs HIDDEN from non-admins in the dashboard. Empty = all visible. Admins always still see hidden tabs. Edit via Admin > Data Controls > Tab Visibility.',
    _last_updated: new Date().toISOString().slice(0,10),
    _last_updated_by: user.email,
    hidden,
  }, null, 2) + '\n';

  try {
    const path = 'data/tab_visibility.json';
    const existing = await ghGetFile({ token, owner, repo, branch, path });
    await ghPutFile({ token, owner, repo, branch, path, content: payload,
      sha: existing ? existing.sha : undefined, message: `tab-config: updated by ${user.email}` });
    return json({ ok: true });
  } catch (e){
    return json({ error: 'github_write_failed', detail: String(e && e.message || e) }, 500);
  }
};

async function isAdmin(context, user){
  const access = await loadAccess(context);
  const entry = (access.users || {})[user.email.toLowerCase()] || (access.users || {})[user.email];
  return !!(entry && (entry.admin === true || entry.role === 'admin'));
}
async function loadAccess(context){
  try {
    const url = new URL(context.request.url); url.pathname = '/access.json';
    const res = await context.env.ASSETS.fetch(url.toString(), { cf: { cacheTtl: 0 } });
    if (res.ok) return await res.json();
  } catch (e){}
  return { users: {} };
}
async function loadConfig(context){
  try {
    const url = new URL(context.request.url); url.pathname = '/data/tab_visibility.json';
    const res = await context.env.ASSETS.fetch(url.toString(), { cf: { cacheTtl: 0 } });
    if (res.ok) return await res.json();
  } catch (e){}
  return { hidden: [] };
}
function json(obj, status=200){
  return new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
}
function ghHeaders(token){
  return { 'authorization': `Bearer ${token}`, 'accept': 'application/vnd.github+json',
    'x-github-api-version': '2022-11-28', 'user-agent': 'bva-marketing-dashboard' };
}
async function ghGetFile({ token, owner, repo, branch, path }){
  const url = `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}?ref=${encodeURIComponent(branch)}`;
  const res = await fetch(url, { headers: ghHeaders(token) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GH GET ${path} ${res.status}`);
  const j = await res.json();
  return { sha: j.sha };
}
async function ghPutFile({ token, owner, repo, branch, path, content, message, sha }){
  const url = `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}`;
  const body = { message, content: btoa(unescape(encodeURIComponent(content))), branch };
  if (sha) body.sha = sha;
  const res = await fetch(url, { method: 'PUT', headers: { ...ghHeaders(token), 'content-type': 'application/json' }, body: JSON.stringify(body) });
  if (!res.ok){ const t = await res.text().catch(()=>res.statusText); throw new Error(`GH PUT ${path} ${res.status}: ${t}`); }
  return await res.json();
}
