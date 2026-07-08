// Site-wide auth gate. Runs on every request to the Pages project.
//
// - If Google auth isn't configured yet (env vars missing), it FAILS OPEN — the site
//   behaves exactly as before (no gate). So deploying this code can't lock anyone out;
//   the gate only turns on once GOOGLE_CLIENT_ID + SESSION_SECRET are set in Cloudflare.
// - Once configured: verifies the signed session cookie, sets context.data.user = {email}
//   for the /api functions, and redirects unauthenticated visitors to Google sign-in.
// - /auth/* is always allowed through (login/callback/logout), else infinite redirect.
import { verifySession } from './_authlib.js';

export const onRequest = async (context) => {
  const { request, next, env, data } = context;
  const url = new URL(request.url);
  const path = url.pathname;

  // Not configured yet -> open (pre-Google-setup behavior; client falls back to local admin).
  if (!env.SESSION_SECRET || !env.GOOGLE_CLIENT_ID) return next();

  // Auth endpoints must always be reachable.
  if (path.startsWith('/auth/')) return next();

  const email = await verifySession(request, env);
  if (email){
    data.user = { email };
    return next();
  }

  // No valid session.
  if (path.startsWith('/api/')){
    return new Response(JSON.stringify({ error: 'unauthenticated' }), {
      status: 401, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' }
    });
  }
  // Page/asset request -> send to Google sign-in, remembering where they were headed.
  const to = encodeURIComponent(path + url.search);
  return Response.redirect(url.origin + '/auth/login?redirect=' + to, 302);
};
