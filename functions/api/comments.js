// GET  /api/comments?slug=member-care&fy=2027
// POST /api/comments
// Body: { slug, fy, fm, account, text }
//
// GET  → returns contents of comments/<slug>__FY<fy>.json from GitHub.
//        If the file does not exist, returns { comments: {} }.
//
// POST → reads existing comments file, updates/adds the comment at key
//        <account>__FM<fm> with { text, user, ts }.  If text is empty
//        string, deletes that key.  Writes updated file back to GitHub
//        and appends one line to audit/<YYYY-MM>.jsonl.
//
// Required env vars (set in Cloudflare Pages → Settings → Environment variables):
//   GITHUB_TOKEN        — fine-grained PAT with Contents: Read+Write on the repo
//   GITHUB_OWNER        — e.g. "devinlindsay-ifit"
//   GITHUB_REPO         — e.g. "bva-member-care-dashboard"
//   GITHUB_BRANCH       — usually "main"

export const onRequestGet = async (context) => {
  const { user } = context.data;
  if (!user || !user.email){
    return json({ error: 'unauthenticated' }, 401);
  }

  const url = new URL(context.request.url);
  const slug = url.searchParams.get('slug');
  const fy   = url.searchParams.get('fy');
  if (!slug || !fy){
    return json({ error: 'missing_fields', need: ['slug', 'fy'] }, 400);
  }

  // Check user has access to this slug
  let access = {};
  try {
    const accessUrl = new URL(context.request.url);
    accessUrl.pathname = '/access.json';
    const res = await context.env.ASSETS.fetch(accessUrl.toString());
    if (res.ok) access = await res.json();
  } catch(e){}
  const userEntry = (access.users || {})[user.email.toLowerCase()] || (access.users || {})[user.email];
  const allowed = userEntry?.slugs;
  if (!userEntry || (allowed !== '*' && !(Array.isArray(allowed) && allowed.includes(slug)))){
    return json({ error: 'forbidden', detail: `${user.email} cannot access ${slug}` }, 403);
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

  const commentsFile = `comments/${slug}__FY${fy}.json`;

  try {
    const existing = await ghGetFile({ token, owner, repo, branch, path: commentsFile });
    if (!existing){
      return json({ comments: {} });
    }
    const parsed = JSON.parse(existing.content);
    return json(parsed);
  } catch (e){
    return json({ error: 'github_read_failed', detail: String(e && e.message || e) }, 500);
  }
};

export const onRequestPost = async (context) => {
  const { user } = context.data;
  if (!user || !user.email){
    return json({ error: 'unauthenticated' }, 401);
  }

  let body;
  try { body = await context.request.json(); } catch(e){
    return json({ error: 'invalid_json' }, 400);
  }
  const { slug, fy, fm, account, text } = body || {};
  if (!slug || !fy || !fm || !account || text === undefined){
    return json({ error: 'missing_fields', need: ['slug', 'fy', 'fm', 'account', 'text'] }, 400);
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

  const commentsFile = `comments/${slug}__FY${fy}.json`;
  const now = new Date();
  const ym  = now.toISOString().slice(0, 7);
  const auditFile = `audit/${ym}.jsonl`;
  const commentKey = `${account}__FM${fm}`;

  try {
    // Read existing comments file (or start fresh)
    const existing = await ghGetFile({ token, owner, repo, branch, path: commentsFile });
    let data = {};
    if (existing){
      try { data = JSON.parse(existing.content); } catch(e){ data = {}; }
    }
    if (!data.comments || typeof data.comments !== 'object') data.comments = {};

    const action = text === '' ? 'delete' : (data.comments[commentKey] ? 'update' : 'add');

    if (text === ''){
      delete data.comments[commentKey];
    } else {
      data.comments[commentKey] = {
        text,
        user: user.email,
        ts: now.toISOString(),
      };
    }

    // Build the updated file payload
    const commentsPayload = JSON.stringify({
      _saved_by: user.email,
      _saved_at: now.toISOString(),
      slug,
      fy: Number(fy),
      comments: data.comments,
    }, null, 2);

    await ghPutFile({ token, owner, repo, branch,
      path: commentsFile,
      content: commentsPayload,
      sha: existing ? existing.sha : undefined,
      message: `comments: ${slug} FY${fy} ${commentKey} ${action} by ${user.email}`,
    });

    // Append audit entry
    const auditEntry = {
      ts: now.toISOString(),
      user: user.email,
      slug,
      fy: Number(fy),
      fm: Number(fm),
      account,
      action,
    };
    const auditLine = JSON.stringify(auditEntry);
    const existingAudit = await ghGetFile({ token, owner, repo, branch, path: auditFile });
    const newAuditContent = (existingAudit ? existingAudit.content + '\n' : '') + auditLine;
    await ghPutFile({ token, owner, repo, branch,
      path: auditFile,
      content: newAuditContent,
      sha: existingAudit ? existingAudit.sha : undefined,
      message: `audit: ${slug} comments by ${user.email}`,
    });

    return json({ ok: true, savedTo: commentsFile, key: commentKey, action, audit: auditEntry });
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
  // Inverse of the write path's btoa(unescape(encodeURIComponent(...))) so
  // UTF-8 chars (em-dash, accents, €) round-trip cleanly instead of mojibake.
  const content = decodeURIComponent(escape(atob((j.content || '').replace(/\n/g,''))));
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
