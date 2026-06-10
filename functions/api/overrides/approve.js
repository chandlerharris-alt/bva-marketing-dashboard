// POST /api/overrides/approve
// Body: { slug, versionKey, source, lineId }
// Admin-only: flips an override entry's status from "saved" to "approved".

export const onRequestPost = async (context) => {
  const { user } = context.data;
  if (!user || !user.email) return json({ error: 'unauthenticated' }, 401);

  let body;
  try { body = await context.request.json(); } catch(e){ return json({ error: 'invalid_json' }, 400); }
  const { slug, versionKey, source, lineId } = body || {};
  if (!slug || !versionKey || !source || !lineId){
    return json({ error: 'missing_fields', need: ['slug','versionKey','source','lineId'] }, 400);
  }

  const role = await getUserRoleForSlug(context, user.email, slug);
  if (role !== 'admin'){
    return json({ error: 'forbidden', detail: 'admin role required to approve overrides' }, 403);
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
    if (!existing){
      return json({ error: 'not_found', detail: 'Override file does not exist' }, 404);
    }
    let fileData = {};
    try { fileData = JSON.parse(existing.content); } catch(e){ fileData = {}; }
    const lines = fileData.lines || {};
    if (!lines[lineId]){
      return json({ error: 'not_found', detail: `lineId ${lineId} not found in override file` }, 404);
    }

    lines[lineId].status = 'approved';
    lines[lineId].reviewed_by = user.email;
    lines[lineId].reviewed_at = now.toISOString();
    fileData.lines = lines;
    fileData._last_updated = now.toISOString();
    fileData._last_updated_by = user.email;

    await ghPutFile({ token, owner, repo, branch,
      path: overridePath,
      sha: existing.sha,
      content: JSON.stringify(fileData, null, 2),
      message: `overrides: ${slug} line ${lineId} approved by ${user.email}`,
    });

    const auditEntry = JSON.stringify({
      kind: 'override_approve',
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
      message: `audit: override_approve ${slug} by ${user.email}`,
    });

    return json({ ok: true, lineId, status: 'approved' });
  } catch(e){
    return json({ error: 'github_write_failed', detail: String(e && e.message || e) }, 500);
  }
};

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
