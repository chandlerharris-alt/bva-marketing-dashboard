// GET  /api/generate-insight?slug=marketing&fy=2027
// POST /api/generate-insight
// Body: { slug, fy, fm, periodLabel, version, metrics }
//
// GET  → returns contents of insights/<slug>__FY<fy>.json from GitHub (all months for that
//        tab+FY). If the file doesn't exist, returns { by_month: {} }. Gated by view access
//        (canSee) — any viewer of the tab can read the latest saved narrative.
//
// POST → calls the Anthropic API with the client-assembled `metrics` summary (top variances +
//        hygiene findings for the current period), writes the returned narrative into
//        insights/<slug>__FY<fy>.json under key FM<fm>, commits it to GitHub, and appends an
//        audit/<YYYY-MM>.jsonl entry. Gated by the 'insight' capability — a per-user, per-tab
//        privilege set in the admin panel (separate from tag/comment/forecast since each
//        generation costs real API spend).
//
// Required env vars (Cloudflare Pages → Settings → Environment variables):
//   ANTHROPIC_API_KEY  — from console.anthropic.com; never paste into chat, only into Cloudflare
//   GITHUB_TOKEN / GITHUB_OWNER / GITHUB_REPO / GITHUB_BRANCH — same as comments.js / access.js
import { getAccess, can, canSee } from '../_access.js';

const MODEL = 'claude-sonnet-5';

const SYSTEM_PROMPT = `You are an FP&A analyst writing a short, honest performance note for an internal marketing budget-vs-actual dashboard. You are given structured JSON with this period's revenue and expense categories (actual vs. plan vs. prior year) and "hygiene" flags (likely missing accruals, missing forecast lines, phantom forecast lines with no recent actuals, and forecast lines running consistently over actuals).

Write 4-7 short bullet points, each starting with "- ". Rules:
- Lead with the single biggest driver of the variance vs Plan, by dollar magnitude, not percentage alone.
- Call out anything where a hygiene flag likely explains part of the story (e.g. "this may partly reflect a missing accrual rather than a true underspend") — don't let a hygiene issue get reported as a real performance win or miss without that caveat.
- Be honest about unfavorable variances. Do not soften bad news or bury it after good news.
- Prefer concrete dollar amounts over vague language.
- No preamble, no headers, no markdown besides the leading "- " on each line. Plain sentences only.`;

export const onRequestGet = async (context) => {
  const { user } = context.data;
  if (!user || !user.email) return json({ error: 'unauthenticated' }, 401);

  const url = new URL(context.request.url);
  const slug = url.searchParams.get('slug');
  const fy   = url.searchParams.get('fy');
  if (!slug || !fy) return json({ error: 'missing_fields', need: ['slug', 'fy'] }, 400);

  const me = await getAccess(context, user.email);
  if (!canSee(me, slug)) return json({ error: 'forbidden', detail: `${user.email} cannot access ${slug}` }, 403);

  const env = context.env || {};
  const token = env.GITHUB_TOKEN, owner = env.GITHUB_OWNER, repo = env.GITHUB_REPO, branch = env.GITHUB_BRANCH || 'main';
  if (!token || !owner || !repo) return json({ error: 'server_misconfigured', detail: 'GITHUB_TOKEN/OWNER/REPO env vars missing' }, 500);

  const insightsFile = `insights/${slug}__FY${fy}.json`;
  try {
    const existing = await ghGetFile({ token, owner, repo, branch, path: insightsFile });
    if (!existing) return json({ by_month: {} });
    return json(JSON.parse(existing.content));
  } catch (e) {
    return json({ error: 'github_read_failed', detail: String(e && e.message || e) }, 500);
  }
};

export const onRequestPost = async (context) => {
  const { user } = context.data;
  if (!user || !user.email) return json({ error: 'unauthenticated' }, 401);

  let body;
  try { body = await context.request.json(); } catch (e) { return json({ error: 'invalid_json' }, 400); }
  const { slug, fy, fm, periodLabel, version, metrics } = body || {};
  if (!slug || !fy || !fm || !metrics) return json({ error: 'missing_fields', need: ['slug', 'fy', 'fm', 'metrics'] }, 400);

  const me = await getAccess(context, user.email);
  if (!can(me, slug, 'insight')) return json({ error: 'forbidden', detail: 'insight access required for this tab' }, 403);

  const env = context.env || {};
  const anthropicKey = env.ANTHROPIC_API_KEY;
  const token = env.GITHUB_TOKEN, owner = env.GITHUB_OWNER, repo = env.GITHUB_REPO, branch = env.GITHUB_BRANCH || 'main';
  if (!anthropicKey) return json({ error: 'server_misconfigured', detail: 'ANTHROPIC_API_KEY env var missing' }, 500);
  if (!token || !owner || !repo) return json({ error: 'server_misconfigured', detail: 'GITHUB_TOKEN/OWNER/REPO env vars missing' }, 500);

  let text;
  try {
    const aiRes = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': anthropicKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 800,
        system: SYSTEM_PROMPT,
        messages: [{ role: 'user', content: `Period: ${periodLabel || (slug + ' FY' + fy)}\nPlan version: ${version || 'n/a'}\n\n${JSON.stringify(metrics)}` }],
      }),
    });
    if (!aiRes.ok) {
      const t = await aiRes.text().catch(() => aiRes.statusText);
      return json({ error: 'anthropic_failed', detail: `HTTP ${aiRes.status}: ${t}` }, 502);
    }
    const aiJson = await aiRes.json();
    text = (aiJson.content || []).map(b => b.text || '').join('').trim();
    if (!text) return json({ error: 'anthropic_empty_response' }, 502);
  } catch (e) {
    return json({ error: 'anthropic_request_failed', detail: String(e && e.message || e) }, 500);
  }

  const insightsFile = `insights/${slug}__FY${fy}.json`;
  const now = new Date();
  const ym = now.toISOString().slice(0, 7);
  const auditFile = `audit/${ym}.jsonl`;
  const fmKey = 'FM' + String(fm).padStart(2, '0');

  try {
    const existing = await ghGetFile({ token, owner, repo, branch, path: insightsFile });
    let data = {};
    if (existing) { try { data = JSON.parse(existing.content); } catch (e) { data = {}; } }
    if (!data.by_month || typeof data.by_month !== 'object') data.by_month = {};

    const entry = { text, version: version || null, periodLabel: periodLabel || null, generatedBy: user.email, generatedAt: now.toISOString() };
    data.by_month[fmKey] = entry;

    const payload = JSON.stringify({ _saved_by: user.email, _saved_at: now.toISOString(), slug, fy: Number(fy), by_month: data.by_month }, null, 2);
    await ghPutFile({ token, owner, repo, branch, path: insightsFile, content: payload, sha: existing ? existing.sha : undefined,
      message: `insight: ${slug} FY${fy} ${fmKey} generated by ${user.email}` });

    const auditEntry = { ts: now.toISOString(), user: user.email, slug, fy: Number(fy), fm: Number(fm), action: 'generate_insight' };
    const existingAudit = await ghGetFile({ token, owner, repo, branch, path: auditFile });
    const newAuditContent = (existingAudit ? existingAudit.content + '\n' : '') + JSON.stringify(auditEntry);
    await ghPutFile({ token, owner, repo, branch, path: auditFile, content: newAuditContent, sha: existingAudit ? existingAudit.sha : undefined,
      message: `audit: ${slug} generate_insight by ${user.email}` });

    return json({ ok: true, entry });
  } catch (e) {
    return json({ error: 'github_write_failed', detail: String(e && e.message || e) }, 500);
  }
};

// ---- helpers ----
function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json' } });
}

async function ghGetFile({ token, owner, repo, branch, path }) {
  const url = `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}?ref=${encodeURIComponent(branch)}`;
  const res = await fetch(url, { headers: ghHeaders(token) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GH GET ${path} ${res.status}`);
  const j = await res.json();
  const content = decodeURIComponent(escape(atob((j.content || '').replace(/\n/g, ''))));
  return { sha: j.sha, content };
}

async function ghPutFile({ token, owner, repo, branch, path, content, message, sha }) {
  const url = `https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}`;
  const body = { message, content: btoa(unescape(encodeURIComponent(content))), branch };
  if (sha) body.sha = sha;
  else {
    const existing = await ghGetFile({ token, owner, repo, branch, path });
    if (existing) body.sha = existing.sha;
  }
  const res = await fetch(url, { method: 'PUT', headers: { ...ghHeaders(token), 'content-type': 'application/json' }, body: JSON.stringify(body) });
  if (!res.ok) {
    const t = await res.text().catch(() => res.statusText);
    throw new Error(`GH PUT ${path} ${res.status}: ${t}`);
  }
  return await res.json();
}

function ghHeaders(token) {
  return {
    'authorization': `Bearer ${token}`,
    'accept': 'application/vnd.github+json',
    'x-github-api-version': '2022-11-28',
    'user-agent': 'bva-marketing-dashboard',
  };
}
