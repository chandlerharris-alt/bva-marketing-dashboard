// POST /api/save-forecast
// Body: { slug, version, source, overrides, summary? }
// Writes overrides/<slug>__<version>__<source>.json to the GitHub repo
// and appends one line to audit/<YYYY-MM>.jsonl for the change log.
//
// Required env vars (set in Cloudflare Pages → Settings → Environment variables):
//   GITHUB_TOKEN        — fine-grained PAT with Contents: Read+Write on the repo
//   GITHUB_OWNER        — e.g. "devinlindsay-ifit"
//   GITHUB_REPO         — e.g. "bva-member-care-dashboard"
//   GITHUB_BRANCH       — usually "main"

export const onRequestPost = async (context) => {
  const { user } = context.data;
  if (!user || !user.email){
    return json({ error: 'unauthenticated' }, 401);
  }

  let body;
  try { body = await context.request.json(); } catch(e){
    return json({ error: 'invalid_json' }, 400);
  }
  const { slug, version, source, overrides, summary, trips, rates } = body || {};
  if (!slug || !version || !source || !overrides){
    return json({ error: 'missing_fields', need: ['slug','version','source','overrides'] }, 400);
  }

  // Check user has access to this slug
  let access = {};
  try {
    const url = new URL(context.request.url);
    url.pathname = '/access.json';
    const res = await context.env.ASSETS.fetch(url.toString());
    if (res.ok) access = await res.json();
  } catch(e){}
  const userEntry = (access.users || {})[user.email.toLowerCase()] || (access.users || {})[user.email];
  const allowed = userEntry?.slugs;
  if (!userEntry || (allowed !== '*' && !(Array.isArray(allowed) && allowed.includes(slug)))){
    return json({ error: 'forbidden', detail: `${user.email} cannot edit ${slug}` }, 403);
  }
  const role = userEntry.role || 'viewer';
  if (role !== 'admin' && role !== 'editor'){
    return json({ error: 'forbidden', detail: 'role does not allow editing' }, 403);
  }

  // Validate env config
  const env = context.env || {};
  const token  = env.GITHUB_TOKEN;
  const owner  = env.GITHUB_OWNER;
  const repo   = env.GITHUB_REPO;
  const branch = env.GITHUB_BRANCH || 'main';
  if (!token || !owner || !repo){
    return json({ error: 'server_misconfigured', detail: 'GITHUB_TOKEN/OWNER/REPO env vars missing' }, 500);
  }

  // File paths to write
  const safeVer = String(version).replace(/[^A-Za-z0-9._+-]/g, '_');
  const overrideFile = `overrides/${slug}__${safeVer}__${source}.json`;
  const now = new Date();
  const ymd = now.toISOString().slice(0,10);
  const ym = ymd.slice(0,7);
  const auditFile = `audit/${ym}.jsonl`;

  // Audit entry — one JSON line per save, append-only
  const auditEntry = {
    ts: now.toISOString(),
    user: user.email,
    slug, version, source,
    summary: summary || null,
    addedCount: Array.isArray(overrides.added) ? overrides.added.length : 0,
    removedCount: Array.isArray(overrides.removed) ? overrides.removed.length : 0,
    editedCount: overrides.edited ? Object.keys(overrides.edited).length : 0,
  };

  try {
    const overridesPayload = JSON.stringify({
      _saved_by: user.email,
      _saved_at: now.toISOString(),
      slug, version, source,
      ...overrides,
      ...(Array.isArray(trips) ? { trips } : {}),
      ...(rates && typeof rates === 'object' ? { rates } : {}),
    }, null, 2);
    await ghPutFile({ token, owner, repo, branch,
      path: overrideFile,
      content: overridesPayload,
      message: `forecast: ${slug} / ${source} updated by ${user.email}`,
    });

    // Append the audit line
    const auditLine = JSON.stringify(auditEntry);
    const existing = await ghGetFile({ token, owner, repo, branch, path: auditFile });
    const newAuditContent = (existing ? existing.content + '\n' : '') + auditLine;
    await ghPutFile({ token, owner, repo, branch,
      path: auditFile,
      content: newAuditContent,
      sha: existing ? existing.sha : undefined,
      message: `audit: ${slug} by ${user.email}`,
    });

    return json({ ok: true, savedTo: overrideFile, audit: auditEntry });
  } catch (e){
    return json({ error: 'github_write_failed', detail: String(e && e.message || e) }, 500);
  }
};

// ---- helpers ----
function json(obj, status=200){
  return new Response(JSON.stringify(obj), {
    status, headers: { 'content-type': 'application/json' }
  });
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
    const t = await res.text().catch(()=>res.statusText);
    throw new Error(`GH PUT ${path} ${res.status}: ${t}`);
  }
  return await res.json();
}

function ghHeaders(token){
  return {
    'authorization': `Bearer ${token}`,
    'accept': 'application/vnd.github+json',
    'x-github-api-version': '2022-11-28',
    'user-agent': 'bva-member-care-dashboard'
  };
}
