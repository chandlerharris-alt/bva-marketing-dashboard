// GET /api/me
// Returns the authenticated user's identity + which sidebar slugs they can access.
// Reads access.json from the deployed bundle (it's part of the Pages build output).
export const onRequestGet = async (context) => {
  const { user } = context.data;
  if (!user || !user.email){
    return new Response(JSON.stringify({ error: 'unauthenticated' }), {
      status: 401, headers: { 'content-type': 'application/json' }
    });
  }

  // Pages serves static assets via context.env.ASSETS — fetch access.json
  // that's bundled with the deploy.
  let access = null;
  try {
    const url = new URL(context.request.url);
    url.pathname = '/access.json';
    const res = await context.env.ASSETS.fetch(url.toString());
    if (res.ok) access = await res.json();
  } catch(e){ /* fall through to default */ }

  const users = (access && access.users) || {};
  const fallback = (access && access._default_for_unlisted_users) || { slugs: [], role: 'denied' };
  const entry = users[user.email.toLowerCase()] || users[user.email] || fallback;

  // Normalize: slugs can be "*" (all) or string[]. Return as either ["*"] or the array.
  const allowedSlugs = entry.slugs === '*' ? ['*'] : (entry.slugs || []);
  const role = entry.role || (allowedSlugs.length ? 'viewer' : 'denied');

  return new Response(JSON.stringify({
    email: user.email,
    role,
    allowedSlugs,
    canEdit: role === 'admin' || role === 'editor',
  }), { headers: { 'content-type': 'application/json' } });
};
