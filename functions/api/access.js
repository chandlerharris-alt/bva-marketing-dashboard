// GET /api/access — return current access.json (admins only)
// POST /api/access — replace access.json (admins only)

export const onRequestGet = async (context) => {
  const { user } = context.data;
  if (!user || !user.email) return json({ error: 'unauthenticated' }, 401);

  const access = await loadAccess(context);
  const myEntry = (access.users || {})[user.email.toLowerCase()] || (access.users || {})[user.email];
  if (!myEntry || myEntry.role !== 'admin'){
    return json({ error: 'forbidden', detail: 'admin role required' }, 403);
  }
  return json(access);
};

export const onRequestPost = async (context) => {
  const { user } = context.data;
  if (!user || !user.email) return json({ error: 'unauthenticated' }, 401);

  const current = await loadAccess(context);
  const myEntry = (current.users || {})[user.email.toLowerCase()] || (current.users || {})[user.email];
  if (!myEntry || myEntry.role !== 'admin'){
    return json({ error: 'forbidden', detail: 'admin role required' }, 403);
  }

  let body;
  try { body = await context.request.json(); } catch(e){ return json({ error: 'invalid_json' }, 400); }
  if (!body || typeof body !== 'object' || !body.users){
    return json({ error: 'missing_users' }, 400);
  }

  const meAfter = body.users[user.email.toLowerCase()] || body.users[user.email];
  if (!meAfter || meAfter.role !== 'admin'){
    return json({ error: 'self_lockout', detail: 'admins must keep their own admin role' }, 400);
  }

  const env = context.env || {};
  const token  = env.GITHUB_TOKEN;
  const owner  = env.GITHUB_OWNER;
  const repo   = env.GITHUB_REPO;
  const branch = env.GITHUB_BRANCH || 'main';
  if (!token || !owner || !repo) return json({ error: 'server_misconfigured' }, 500);

  const newAccess = {
    _comment: current._comment || 'User email -> allowed sidebar slugs. Use \'*\' for all tabs. Admins can edit via /admin in the dashboard.',
    _last_updated: new Date().toISOString().slice(0,10),
    _last_updated_by: user.email,
    users: body.users,
    _default_for_unlisted_users: body._default_for_unlisted_users || current._default_for_unlisted_users || { slugs: [], role: 'denied' },
  };

  try {
    const path = 'access.json';
    const existing = await ghGetFile({ token, owner, repo, branch, path });
    const payload = JSON.stringify(newAccess, null, 2);
    await ghPutFile({
      token, owner, repo, branch, path,
      content: payload,
      sha: existing ? existing.sha : undefined,
      message: `access: updated by ${user.email}`,
    });

    const ym = new Date().toISOString().slice(0,7);
    const auditFile = `audit/${ym}.jsonl`;
    const existingAudit = await ghGetFile({ token, owner, repo, branch, path: auditFile });
    const line = JSON.stringify({
      ts: new Date().toISOString(),
      user: user.email,
      kind: 'access_change',
      userCount: Object.keys(body.users).length,
    });
    const newAuditContent = (existingAudit ? existingAudit.content + '\n' : '') + line;
    await ghPutFile({
      token, owner, repo, branch, path: auditFile,
      content: newAuditContent,
      sha: existingAudit ? existingAudit.sha : undefined,
      message: `audit: access change by ${user.email}`,
    });

    return json({ ok: true });
  } catch (e){
    return json({ error: 'github_write_failed', detail: String(e && e.message || e) }, 500);
  }
};

async function loadAccess(context){
  try {
    const url = new URL(context.request.url);
    url.pathname = '/access.json';
    const res = await context.env.ASSETS.fetch(url.toString(), { cf: { cacheTtl: 0 } });
    if (res.ok) return await res.json();
  } catch (e){}
  return { users: {} };
}

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
