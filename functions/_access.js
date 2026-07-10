// Shared access-control helper for the API functions. Reads access.json and evaluates the
// v2 schema: each user = { admin, tabs:{slug->{view,tag,comment,forecast}, '*'=default}, versions }.
// Old {role, slugs} entries are migrated on the fly (keep in sync with me.js normalizeEntry).

export async function loadAccessJson(context){
  try {
    const url = new URL(context.request.url); url.pathname = '/access.json';
    const res = await context.env.ASSETS.fetch(url.toString(), { cf: { cacheTtl: 0 } });
    if (res.ok) return await res.json();
  } catch(e){}
  return { users: {} };
}

export function normalizeEntry(entry){
  if (!entry) return { admin:false, tabs:{}, versions:'*' };
  if (entry.tabs || entry.admin !== undefined){
    return { admin: !!entry.admin, tabs: entry.tabs || {}, versions: entry.versions || '*' };
  }
  const role = entry.role || 'denied';
  if (role === 'admin') return { admin:true, tabs:{ '*':{view:true,tag:true,comment:true,forecast:true} }, versions:'*' };
  const caps = role === 'editor' ? {view:true,tag:true,comment:true,forecast:true}
             : role === 'viewer' ? {view:true} : null;
  if (!caps) return { admin:false, tabs:{}, versions:'*' };
  const tabs = {};
  if (entry.slugs === '*') tabs['*'] = caps;
  else (entry.slugs || []).forEach(s => { tabs[s] = caps; });
  return { admin:false, tabs, versions:'*' };
}

// Normalized entry for an email (with the unlisted-user default applied).
export async function getAccess(context, email){
  const access = await loadAccessJson(context);
  const users = access.users || {};
  const emailKey = (email || '').trim().toLowerCase();
  const raw = users[emailKey] || users[(email || '').trim()] || users[email] || access._default_for_unlisted_users || null;
  return normalizeEntry(raw);
}

export function isAdmin(entry){ return !!(entry && entry.admin); }
export function tabCaps(entry, slug){
  if (entry && entry.admin) return { view:true, tag:true, comment:true, forecast:true, insight:true };
  const t = (entry && entry.tabs) || {};
  return Object.assign({}, t['*'] || {}, t[slug] || {});
}
// cap = 'view' | 'tag' | 'comment' | 'forecast' | 'insight'
export function can(entry, slug, cap){ return (entry && entry.admin === true) || !!tabCaps(entry, slug)[cap]; }
export function canSee(entry, slug){
  const c = tabCaps(entry, slug);
  return (entry && entry.admin === true) || !!(c.view || c.tag || c.comment || c.forecast);
}
