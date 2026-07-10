// GET  /api/txn-types
// POST /api/txn-types
// Body: { mappings: { "<RAW_CODE>": "Invoice"|"Accrual"|"Reversal"|"JE"|"Other" } }
//
// GET  → returns the full contents of data-controls/txn-types.json from GitHub
//        (one shared file — the mapping is a global setting, not per-tab).
//        Anyone signed in can read it (needed to render the color-coded tag for
//        everyone), even though only admins can change it.
//
// POST → admin-only. Merges the given mappings into the existing file (so two
//        admins editing different rows don't clobber each other) and writes it
//        back to GitHub.
//
// Required env vars (set in Cloudflare Pages -> Settings -> Environment variables):
//   GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH
import { getAccess, isAdmin } from '../_access.js';

const TXN_TYPES_FILE = 'data-controls/txn-types.json';

export const onRequestGet = async (context) => {
  const { user } = context.data;
  if (!user || !user.email){
    return json({ error: 'unauthenticated' }, 401);
  }

  const env = context.env || {};
  const token  = env.GITHUB_TOKEN;
  const owner  = env.GITHUB_OWNER;
  const repo   = env.GITHUB_REPO;
  const branch = env.GITHUB_BRANCH || 'main';
  if (!token || !owner || !repo){
    return json({ error: 'server_misconfigured', detail: 'GITHUB_TOKEN/OWNER/REPO env vars missing' }, 500);
  }

  try {
    const existing = await ghGetFile({ token, owner, repo, branch, path: TXN_TYPES_FILE });
    if (!existing) return json({ mappings: {} });
    const parsed = JSON.parse(existing.content);
    if (!parsed.mappings || typeof parsed.mappings !== 'object') parsed.mappings = {};
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
  const { mappings } = body || {};
  if (!mappings || typeof mappings !== 'object'){
    return json({ error: 'missing_fields', need: ['mappings'] }, 400);
  }

  const me = await getAccess(context, user.email);
  if (!isAdmin(me)){
    return json({ error: 'forbidden', detail: 'admin access required' }, 403);
  }

  const env = context.env || {};
  const token  = env.GITHUB_TOKEN;
  const owner  = env.GITHUB_OWNER;
  const repo   = env.GITHUB_REPO;
  const branch = env.GITHUB_BRANCH || 'main';
  if (!token || !owner || !repo){
    return json({ error: 'server_misconfigured', detail: 'GITHUB_TOKEN/OWNER/REPO env vars missing' }, 500);
  }

  const now = new Date();
  const ym  = now.toISOString().slice(0, 7);
  const auditFile = `audit/${ym}.jsonl`;

  try {
    const existing = await ghGetFile({ token, owner, repo, branch, path: TXN_TYPES_FILE });
    let data = {};
    if (existing){
      try { data = JSON.parse(existing.content); } catch(e){ data = {}; }
    }
    if (!data.mappings || typeof data.mappings !== 'object') data.mappings = {};

    const changed = [];
    Object.entries(mappings).forEach(([code, bucket]) => {
      if (bucket === null || bucket === ''){
        if (data.mappings[code] !== undefined){ delete data.mappings[code]; changed.push(code); }
      } else if (data.mappings[code] !== bucket){
        data.mappings[code] = bucket;
        changed.push(code);
      }
    });

    const payload = JSON.stringify({
      _saved_by: user.email,
      _saved_at: now.toISOString(),
      mappings: data.mappings,
    }, null, 2);

    await ghPutFile({ token, owner, repo, branch,
      path: TXN_TYPES_FILE,
      content: payload,
      sha: existing ? existing.sha : undefined,
      message: `txn-types: ${changed.join(', ') || 'no-op'} updated by ${user.email}`,
    });

    if (changed.length){
      const auditEntry = { ts: now.toISOString(), user: user.email, action: 'txn-type-mapping', changed: changed.map(c => ({ code: c, bucket: mappings[c] })) };
      const auditLine = JSON.stringify(auditEntry);
      const existingAudit = await ghGetFile({ token, owner, repo, branch, path: auditFile });
      const newAuditContent = (existingAudit ? existingAudit.content + '\n' : '') + auditLine;
      await ghPutFile({ token, owner, repo, branch,
        path: auditFile,
        content: newAuditContent,
        sha: existingAudit ? existingAudit.sha : undefined,
        message: `audit: txn-types by ${user.email}`,
      });
    }

    return json({ ok: true, changed });
  } catch (e){
    return json({ error: 'github_write_failed', detail: String(e && e.message || e) }, 500);
  }
};

// ---- helpers ----
function json(obj, status=200){
  return new Response(JSON.stringify(obj), {
    status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' }
  });
}

async function ghGetFile({ token, owner, repo, branch, path }){
  const url = `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}?ref=${encodeURIComponent(branch)}`;
  const res = await fetch(url, { headers: ghHeaders(token) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GH GET ${path} ${res.status}`);
  const j = await res.json();
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
