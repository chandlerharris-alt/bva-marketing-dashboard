// GET /auth/callback — Google redirects here with ?code&state.
// Verifies CSRF state, exchanges the code for tokens (server-side, using the client secret),
// checks the email domain, then sets a signed session cookie and returns the user to the app.
import { getCookie, decodeJwtPayload, makeSession, allowedDomains, htmlMessage, base64urlDecodeToString } from '../_authlib.js';

export const onRequestGet = async (context) => {
  const { request, env } = context;
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const stateCookie = getCookie(request, 'oauth_state');

  if (!code || !state || !stateCookie || state !== stateCookie){
    return htmlMessage('Sign-in failed', 'The sign-in request expired or didn’t match. Please try again.', { signin: true, status: 400 });
  }
  if (!env.GOOGLE_CLIENT_SECRET || !env.SESSION_SECRET){
    return htmlMessage('Sign-in not configured', 'Google sign-in isn’t fully configured yet. Please contact the administrator.', { status: 500 });
  }

  // Exchange the authorization code for tokens.
  const redirectUri = url.origin + '/auth/callback';
  const body = new URLSearchParams({
    code,
    client_id: env.GOOGLE_CLIENT_ID,
    client_secret: env.GOOGLE_CLIENT_SECRET,
    redirect_uri: redirectUri,
    grant_type: 'authorization_code',
  });
  let claims;
  try {
    const res = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body,
    });
    if (!res.ok) throw new Error('token ' + res.status);
    const tokens = await res.json();
    // The id_token comes straight from Google's token endpoint over TLS, so its claims
    // are trustworthy here without separate signature verification.
    claims = decodeJwtPayload(tokens.id_token);
  } catch(e){
    return htmlMessage('Sign-in failed', 'Could not complete sign-in with Google. Please try again.', { signin: true, status: 502 });
  }

  const email = (claims.email || '').toLowerCase();
  const domain = email.split('@')[1] || '';
  const allowed = allowedDomains(env);
  if (!claims.email_verified || !allowed.includes(domain)){
    return htmlMessage('Access restricted',
      `This dashboard is limited to ${allowed.join(' / ')} accounts. You signed in as <b style="color:#F2FEFF">${email || 'an unrecognized account'}</b>.`,
      { switchAccount: true, status: 403 });
  }

  // Success -> 12-hour signed session cookie, then back to where they were headed.
  const session = await makeSession(email, env.SESSION_SECRET, 12 * 60 * 60 * 1000);
  let dest = '/dashboard/index.html';
  try { const s = JSON.parse(base64urlDecodeToString(state)); if (s.r) dest = s.r; } catch(e){}
  if (!dest.startsWith('/')) dest = '/dashboard/index.html';   // only allow same-site paths

  const headers = new Headers({ 'Location': url.origin + dest });
  headers.append('Set-Cookie', `session=${session}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${12 * 60 * 60}`);
  headers.append('Set-Cookie', `oauth_state=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`);
  return new Response(null, { status: 302, headers });
};
