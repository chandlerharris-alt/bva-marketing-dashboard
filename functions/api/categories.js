// GET  /api/categories?slug=<slug>  → return saved categories + desc mapping
// POST /api/categories               → body: { slug, categories, descToCategory }
import { getAccess, can, canSee } from '../_access.js';

export const onRequestGet = async (context) => {
  const { user } = context.data;
  if (!user || !user.email) return json({ error: 'unauthenticated' }, 401);

  const url = new URL(context.request.url);
  const slug = url.searchParams.get('slug');
  if (!slug) return json({ error: 'missing_slug' }, 400);

  const me = await getAccess(context, user.email);
  if (!canSee(me, slug)) return json({ error: 'forbidden' }, 403);

  const env = context.env || {};
  const token = env.GITHUB_TOKEN, owner = env.GITHUB_OWNER, repo = env.GITHUB_REPO;
  const branch = env.GITHUB_BRANCH || 'main';
  if (!token || !owner || !repo) return json({ error: 'server_misconfigured' }, 500);

  try {
    const path = `categories/${slug}.json`;
    const res = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}?ref=${encodeURIComponent(branch)}`,
      { headers: ghHeaders(token) }
    );
    if (res.status === 404) return json({ slug, categories: [], descToCategory: {} });
    if (!res.ok) throw new Error('GH GET ' + res.status);
    const j = await res.json();
    const raw = atob((j.content || '').replace(/\n/g, ''));
    const parsed = JSON.parse(raw);
    return json({ slug, ...parsed });
  } catch (e) {
    return json({ error: 'github_read_failed', detail: String(e && e.message || e) }, 500);
  }
};

export const onRequestPost = async (context) => {
  const { user } = context.data;
  if (!user || !user.email) return json({ error: 'unauthenticated' }, 401);

  let body;
  try { body = await context.request.json(); } catch (e) { return json({ error: 'invalid_json' }, 400); }
  const { slug, categories, descToCategory, descToCategoryByAcct } = body || {};
  if (!slug || !Array.isArray(categories) || typeof descToCategory !== 'object'){
    return json({ error: 'missing_fields' }, 400);
  }
  const perAcct = (descToCategoryByAcct && typeof descToCategoryByAcct === 'object') ? descToCategoryByAcct : {};

  const me = await getAccess(context, user.email);
  if (!can(me, slug, 'tag')){
    return json({ error: 'forbidden', detail: 'tag-edit access required for this tab' }, 403);
  }

  const env = context.env || {};
  const token = env.GITHUB_TOKEN, owner = env.GITHUB_OWNER, repo = env.GITHUB_REPO;
  const branch = env.GITHUB_BRANCH || 'main';
  if (!token || !owner || !repo) return json({ error: 'server_misconfigured' }, 500);

  const path = `categories/${slug}.json`;
  const now = new Date();
  const payload = JSON.stringify({
    _last_updated: now.toISOString(),
    _last_updated_by: user.email,
    slug,
    categories,
    descToCategory,
    descToCategoryByAcct: perAcct,
  }, null, 2);

  try {
    const existing = await ghGetFile({ token, owner, repo, branch, path });
    await ghPutFile({
      token, owner, repo, branch, path,
      content: payload,
      sha: existing ? existing.sha : undefined,
      message: `categories: ${slug} updated by ${user.email}`,
    });
    return json({ ok: true });
  } catch (e) {
    return json({ error: 'github_write_failed', detail: String(e && e.message || e) }, 500);
  }
};

// ---- helpers ----
async function loadAccess(context){
  try {
    const u = new URL(context.request.url);
    u.pathname = '/access.json';
    const r = await context.env.ASSETS.fetch(u.toString());
    if (r.ok) return await r.json();
  } catch (e) {}
  return { users: {} };
}
async function checkUserAllowedForSlug(context, email, slug){
  const access = await loadAccess(context);
  const entry = (access.users || {})[email.toLowerCase()] || (access.users || {})[email];
  if (!entry || entry.role === 'denied') return false;
  const allowed = entry.slugs;
  return allowed === '*' || (Array.isArray(allowed) && allowed.includes(slug));
}
async function getUserRoleForSlug(context, email, slug){
  const access = await loadAccess(context);
  const entry = (access.users || {})[email.toLowerCase()] || (access.users || {})[email];
  if (!entry) return 'denied';
  const allowed = entry.slugs;
  if (allowed !== '*' && !(Array.isArray(allowed) && allowed.includes(slug))) return 'denied';
  return entry.role || 'viewer';
}
function json(obj, status=200){
  return new Response(JSON.stringify(obj), {
    status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' }
  });
}
function ghHeaders(token){
  return {
    'authorization': `Bearer ${token}`,
    'accept': 'application/vnd.github+json',
    'x-github-api-version': '2022-11-28',
    'user-agent': 'bva-member-care-dashboard'
  };
}
async function ghGetFile({ token, owner, repo, branch, path }){
  const url = `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}?ref=${encodeURIComponent(branch)}`;
  const res = await fetch(url, { headers: ghHeaders(token) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GH GET ${path} ${res.status}`);
  const j = await res.json();
  const content = atob((j.content || '').replace(/\n/g, ''));
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
  const res = await fetch(url, {
    method: 'PUT',
    headers: { ...ghHeaders(token), 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok){
    const t = await res.text().catch(()=>res.statusText);
    throw new Error(`GH PUT ${path} ${res.status}: ${t}`);
  }
  return await res.json();
}
