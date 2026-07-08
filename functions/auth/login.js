// GET /auth/login — start the Google OAuth authorization-code flow.
// Redirects the browser to Google's consent screen; stashes a CSRF state cookie that
// also carries where to return the user after sign-in.
import { base64urlEncode, randomState, allowedDomains, htmlMessage } from '../_authlib.js';

export const onRequestGet = async (context) => {
  const { request, env } = context;
  const url = new URL(request.url);
  if (!env.GOOGLE_CLIENT_ID){
    return htmlMessage('Sign-in not configured', 'The dashboard administrator hasn’t finished setting up Google sign-in yet.');
  }
  const redirectTo = url.searchParams.get('redirect') || '/dashboard/index.html';
  const state = base64urlEncode(JSON.stringify({ r: redirectTo, n: randomState() }));
  const redirectUri = url.origin + '/auth/callback';

  const auth = new URL('https://accounts.google.com/o/oauth2/v2/auth');
  auth.searchParams.set('client_id', env.GOOGLE_CLIENT_ID);
  auth.searchParams.set('redirect_uri', redirectUri);
  auth.searchParams.set('response_type', 'code');
  auth.searchParams.set('scope', 'openid email profile');
  auth.searchParams.set('state', state);
  auth.searchParams.set('access_type', 'online');
  auth.searchParams.set('prompt', 'select_account');
  const hd = allowedDomains(env)[0];
  if (hd) auth.searchParams.set('hd', hd);   // hint the org domain (not a hard lock; we re-check in callback)

  const headers = new Headers({ 'Location': auth.toString() });
  headers.append('Set-Cookie', `oauth_state=${state}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=600`);
  return new Response(null, { status: 302, headers });
};
