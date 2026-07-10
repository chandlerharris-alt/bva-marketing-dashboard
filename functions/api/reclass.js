// GET  /api/reclass
// POST /api/reclass
// Body: { action: 'upsert'|'delete', slug, suggestion } or { action:'delete', slug, id }
//
// GET  → returns the full contents of reclass/suggestions.json from GitHub
//        (one shared file across every tab, since the summary tab needs
//        everything in one place). If the file does not exist, returns
//        { suggestions: {} }.
//
// POST → reads the existing file, adds/replaces or deletes ONE key by
//        suggestion.id (safe against two people submitting concurrently —
//        never blind-replaces the whole file the way categories.js does),
//        writes it back to GitHub, and appends one line to
//        audit/<YYYY-MM>.jsonl.
//
// Required env vars (set in Cloudflare Pages → Settings → Environment variables):
//   GITHUB_TOKEN        — fine-grained PAT with Contents: Read+Write on the repo
//   GITHUB_OWNER
//   GITHUB_REPO
//   GITHUB_BRANCH       — usually "main"
import { getAccess, can } from '../_access.js';

const RECLASS_FILE = 'reclass/suggestions.json';

export const onRequestGet = async (context) => {
  const { user } = context.data;
  if (!user || !user.email){
    return json({ error: 'unauthenticated' }, 401);
  }

  // Suggestions span every tab, so gate on "has at least one granted tab"
  // rather than a single slug's canSee (there's no one slug to check here).
  const me = await getAccess(context, user.email);
  const hasAnyGrantedTab = me.admin || Object.values(me.tabs || {}).some(c =>
    c && (c.view || c.tag || c.comment || c.forecast || c.insight));
  if (!hasAnyGrantedTab){
    return json({ error: 'forbidden' }, 403);
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
    const existing = await ghGetFile({ token, owner, repo, branch, path: RECLASS_FILE });
    if (!existing) return json({ suggestions: {} });
    const parsed = JSON.parse(existing.content);
    if (!parsed.suggestions || typeof parsed.suggestions !== 'object') parsed.suggestions = {};
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
  const { action, slug } = body || {};
  if (!slug || (action !== 'upsert' && action !== 'delete')){
    return json({ error: 'missing_fields', need: ['slug', "action: 'upsert'|'delete'"] }, 400);
  }
  const id = action === 'upsert' ? (body.suggestion && body.suggestion.id) : body.id;
  if (!id){
    return json({ error: 'missing_fields', need: ['id (or suggestion.id for upsert)'] }, 400);
  }
  if (action === 'upsert'){
    const s = body.suggestion;
    if (!s || !s.from_account || !s.to_account || s.fy == null || s.fm == null){
      return json({ error: 'missing_fields', need: ['suggestion.from_account', 'suggestion.to_account', 'suggestion.fy', 'suggestion.fm'] }, 400);
    }
  }

  // Reuse the same 'tag' capability the transaction-tagging feature already
  // requires — reclass suggestions are the same kind of per-transaction
  // annotation, scoped to whichever tab the suggestion belongs to.
  const me = await getAccess(context, user.email);
  if (!can(me, slug, 'tag')){
    return json({ error: 'forbidden', detail: 'tag access required for this tab' }, 403);
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
    const existing = await ghGetFile({ token, owner, repo, branch, path: RECLASS_FILE });
    let data = {};
    if (existing){
      try { data = JSON.parse(existing.content); } catch(e){ data = {}; }
    }
    if (!data.suggestions || typeof data.suggestions !== 'object') data.suggestions = {};

    let auditAction;
    if (action === 'delete'){
      auditAction = data.suggestions[id] ? 'delete' : 'noop';
      delete data.suggestions[id];
    } else {
      auditAction = data.suggestions[id] ? 'update' : 'add';
      data.suggestions[id] = {
        ...body.suggestion,
        slug,
        created_by: body.suggestion.created_by || user.email,
        created_at: body.suggestion.created_at || now.toISOString(),
      };
    }

    const payload = JSON.stringify({
      _saved_by: user.email,
      _saved_at: now.toISOString(),
      suggestions: data.suggestions,
    }, null, 2);

    await ghPutFile({ token, owner, repo, branch,
      path: RECLASS_FILE,
      content: payload,
      sha: existing ? existing.sha : undefined,
      message: `reclass: ${slug} ${id} ${auditAction} by ${user.email}`,
    });

    const auditEntry = { ts: now.toISOString(), user: user.email, slug, id, action: auditAction };
    if (action === 'upsert' && body.suggestion){
      auditEntry.from_account = body.suggestion.from_account;
      auditEntry.to_account = body.suggestion.to_account;
      auditEntry.amount_snapshot = body.suggestion.amount_snapshot;
    }
    const auditLine = JSON.stringify(auditEntry);
    const existingAudit = await ghGetFile({ token, owner, repo, branch, path: auditFile });
    const newAuditContent = (existingAudit ? existingAudit.content + '\n' : '') + auditLine;
    await ghPutFile({ token, owner, repo, branch,
      path: auditFile,
      content: newAuditContent,
      sha: existingAudit ? existingAudit.sha : undefined,
      message: `audit: ${slug} reclass by ${user.email}`,
    });

    return json({ ok: true, id, action: auditAction });
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
