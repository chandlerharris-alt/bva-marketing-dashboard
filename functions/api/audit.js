// GET /api/audit?slug=<slug>&limit=20
// Returns the most recent audit log entries (filtered by slug if provided).
export const onRequestGet = async (context) => {
  const { user } = context.data;
  if (!user || !user.email){
    return new Response(JSON.stringify({ error: 'unauthenticated' }), { status: 401, headers: { 'content-type': 'application/json' } });
  }
  let access = {};
  try {
    const u = new URL(context.request.url);
    u.pathname = '/access.json';
    const r = await context.env.ASSETS.fetch(u.toString());
    if (r.ok) access = await r.json();
  } catch (e){}
  const entry = (access.users || {})[user.email.toLowerCase()] || (access.users || {})[user.email];
  if (!entry || entry.role === 'denied'){
    return new Response(JSON.stringify({ error: 'forbidden' }), { status: 403, headers: { 'content-type': 'application/json' } });
  }
  const url = new URL(context.request.url);
  const slug = url.searchParams.get('slug');
  const limit = Math.min(200, parseInt(url.searchParams.get('limit') || '20', 10));
  const allowed = entry.slugs;
  const slugFilter = (s) => allowed === '*' || (Array.isArray(allowed) && allowed.includes(s));

  const env = context.env || {};
  const token  = env.GITHUB_TOKEN;
  const owner  = env.GITHUB_OWNER;
  const repo   = env.GITHUB_REPO;
  const branch = env.GITHUB_BRANCH || 'main';

  const now = new Date();
  const months = [];
  for (let i = 0; i < 3; i++){
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push(d.toISOString().slice(0,7));
  }

  const entries = [];
  for (const ym of months){
    const path = `audit/${ym}.jsonl`;
    const res = await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/${encodeURIComponent(path)}?ref=${encodeURIComponent(branch)}`,
      { headers: ghHeaders(token) });
    if (res.status === 404) continue;
    if (!res.ok) continue;
    const j = await res.json();
    const text = atob((j.content || '').replace(/\n/g,''));
    text.split('\n').forEach(line => {
      if (!line.trim()) return;
      try {
        const obj = JSON.parse(line);
        if (slug && obj.slug !== slug) return;
        if (entry.role !== 'admin' && obj.slug && !slugFilter(obj.slug)) return;
        entries.push(obj);
      } catch(e){}
    });
  }

  entries.sort((a,b) => (b.ts||'').localeCompare(a.ts||''));
  return new Response(JSON.stringify({ entries: entries.slice(0, limit) }),
    { headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
};

function ghHeaders(token){
  return {
    'authorization': `Bearer ${token}`,
    'accept': 'application/vnd.github+json',
    'x-github-api-version': '2022-11-28',
    'user-agent': 'bva-member-care-dashboard'
  };
}
