// GET  /api/variance-allocations
// POST /api/variance-allocations
// Body: { action: 'submit'|'approve'|'delete', allocation } or { action:'approve'|'delete', id }
//
// GET  → returns the full contents of variance/allocations.json from GitHub (one shared
//        file across every region, since the Variance Investment/Divestment tab needs
//        everything in one place, same shape as reclass.js). If the file does not exist,
//        returns { allocations: {} }.
//
// POST → reads the existing file, adds/replaces/updates or deletes ONE key by
//        allocation.id (safe against two people submitting concurrently — never
//        blind-replaces the whole file), writes it back to GitHub, and appends one
//        line to audit/<YYYY-MM>.jsonl.
//
// 'approve' appends the calling admin's email to allocation.approved_by (rejecting a
// duplicate same-admin approval); once approved_by has >= 2 distinct admin emails the
// allocation is considered approved (computed client-side + re-checked here).
//
// Required env vars (same as reclass.js):
//   GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH
import { getAccess, can, isAdmin } from '../_access.js';

const ALLOC_FILE = 'variance/allocations.json';

export const onRequestGet = async (context) => {
  const { user } = context.data;
  if (!user || !user.email){
    return json({ error: 'unauthenticated' }, 401);
  }

  // Same "has at least one granted tab" gate as reclass.js — allocations aren't
  // scoped to a single slug, they roll up marketing + media by region.
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
    const existing = await ghGetFile({ token, owner, repo, branch, path: ALLOC_FILE });
    if (!existing) return json({ allocations: {} });
    const parsed = JSON.parse(existing.content);
    if (!parsed.allocations || typeof parsed.allocations !== 'object') parsed.allocations = {};
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
  const { action } = body || {};
  if (action !== 'submit' && action !== 'approve' && action !== 'delete'){
    return json({ error: 'missing_fields', need: ["action: 'submit'|'approve'|'delete'"] }, 400);
  }
  const id = action === 'submit' ? (body.allocation && body.allocation.id) : body.id;
  if (!id){
    return json({ error: 'missing_fields', need: ['id (or allocation.id for submit)'] }, 400);
  }
  if (action === 'submit'){
    const a = body.allocation;
    if (!a || !a.region || a.amount == null || a.target_fy == null || a.target_fm == null){
      return json({ error: 'missing_fields', need: ['allocation.region', 'allocation.amount', 'allocation.target_fy', 'allocation.target_fm'] }, 400);
    }
  }

  const me = await getAccess(context, user.email);
  if (action === 'approve'){
    if (!isAdmin(me)){
      return json({ error: 'forbidden', detail: 'admin required to approve' }, 403);
    }
  } else {
    // submit/delete — reuse the 'forecast' capability on either marketing-family tab,
    // same reasoning as reclass.js reusing 'tag': this is the closest existing
    // capability to "may edit planning/forecast data," and allocations aren't
    // scoped to one single tab.
    if (!can(me, 'marketing', 'forecast') && !can(me, 'media', 'forecast')){
      return json({ error: 'forbidden', detail: 'forecast access required' }, 403);
    }
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
    const existing = await ghGetFile({ token, owner, repo, branch, path: ALLOC_FILE });
    let data = {};
    if (existing){
      try { data = JSON.parse(existing.content); } catch(e){ data = {}; }
    }
    if (!data.allocations || typeof data.allocations !== 'object') data.allocations = {};

    let auditAction;
    if (action === 'delete'){
      auditAction = data.allocations[id] ? 'delete' : 'noop';
      delete data.allocations[id];
    } else if (action === 'approve'){
      const rec = data.allocations[id];
      if (!rec){
        return json({ error: 'not_found' }, 404);
      }
      const approvedBy = Array.isArray(rec.approved_by) ? rec.approved_by.slice() : [];
      if (approvedBy.includes(user.email)){
        return json({ error: 'already_approved_by_you' }, 409);
      }
      approvedBy.push(user.email);
      rec.approved_by = approvedBy;
      rec.status = approvedBy.length >= 2 ? 'approved' : 'pending';
      auditAction = rec.status === 'approved' ? 'approved' : 'partial_approval';
    } else {
      const isUpdate = !!data.allocations[id];
      auditAction = isUpdate ? 'update' : 'add';
      const prior = data.allocations[id] || {};
      data.allocations[id] = {
        ...body.allocation,
        id,
        status: prior.status || 'pending',
        approved_by: prior.approved_by || [],
        created_by: prior.created_by || body.allocation.created_by || user.email,
        created_at: prior.created_at || body.allocation.created_at || now.toISOString(),
      };
    }

    const payload = JSON.stringify({
      _saved_by: user.email,
      _saved_at: now.toISOString(),
      allocations: data.allocations,
    }, null, 2);

    await ghPutFile({ token, owner, repo, branch,
      path: ALLOC_FILE,
      content: payload,
      sha: existing ? existing.sha : undefined,
      message: `variance-allocations: ${id} ${auditAction} by ${user.email}`,
    });

    const auditEntry = { ts: now.toISOString(), user: user.email, id, action: auditAction };
    if (action === 'submit' && body.allocation){
      auditEntry.region = body.allocation.region;
      auditEntry.amount = body.allocation.amount;
      auditEntry.target_fy = body.allocation.target_fy;
      auditEntry.target_fm = body.allocation.target_fm;
    }
    const auditLine = JSON.stringify(auditEntry);
    const existingAudit = await ghGetFile({ token, owner, repo, branch, path: auditFile });
    const newAuditContent = (existingAudit ? existingAudit.content + '\n' : '') + auditLine;
    await ghPutFile({ token, owner, repo, branch,
      path: auditFile,
      content: newAuditContent,
      sha: existingAudit ? existingAudit.sha : undefined,
      message: `audit: variance-allocations by ${user.email}`,
    });

    return json({ ok: true, id, action: auditAction, record: data.allocations[id] || null });
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
