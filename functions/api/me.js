// GET /api/me
// Returns the authenticated user's identity + per-tab capabilities + version allow-list.
// Reads access.json from the deployed bundle. Identity comes from context.data.user, set by
// functions/_middleware.js (Google sign-in). Until that gate is wired, this 401s and the
// client falls back to full local access.
export const onRequestGet = async (context) => {
  const { user } = context.data || {};
  if (!user || !user.email){
    return json({ error: 'unauthenticated' }, 401);
  }

  let access = null;
  try {
    const url = new URL(context.request.url);
    url.pathname = '/access.json';
    // cacheTtl:0 — without this, ASSETS.fetch can serve a cached copy of access.json from
    // before the latest admin save, so a newly-granted user still gets the unlisted-user
    // default (no tabs) even after a fresh deploy. _access.js (used by every other endpoint)
    // already disables caching here; this endpoint had been missing it.
    const res = await context.env.ASSETS.fetch(url.toString(), { cf: { cacheTtl: 0 } });
    if (res.ok) access = await res.json();
  } catch(e){ /* fall through to default */ }

  const users = (access && access.users) || {};
  const fallback = (access && access._default_for_unlisted_users) || null;
  const emailKey = user.email.trim().toLowerCase();
  const raw = users[emailKey] || users[user.email.trim()] || users[user.email] || fallback;
  const norm = normalizeEntry(raw);

  return json({
    email: user.email,
    admin: norm.admin,
    tabs: norm.tabs,
    versions: norm.versions,
  });
};

// Migrate old {role, slugs} entries to the new {admin, tabs, versions} shape.
function normalizeEntry(entry){
  if (!entry) return { admin:false, tabs:{}, versions:'*' };
  if (entry.tabs || entry.admin !== undefined){
    return { admin: !!entry.admin, tabs: entry.tabs || {}, versions: entry.versions || '*' };
  }
  const role = entry.role || 'denied';
  if (role === 'admin') return { admin:true, tabs:{ '*':{view:true,tag:true,comment:true,forecast:true,insight:true} }, versions:'*' };
  const caps = role === 'editor' ? {view:true,tag:true,comment:true,forecast:true}
             : role === 'viewer' ? {view:true} : null;
  if (!caps) return { admin:false, tabs:{}, versions:'*' };
  const tabs = {};
  if (entry.slugs === '*') tabs['*'] = caps;
  else (entry.slugs || []).forEach(s => { tabs[s] = caps; });
  return { admin:false, tabs, versions:'*' };
}

function json(obj, status=200){
  return new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
}
