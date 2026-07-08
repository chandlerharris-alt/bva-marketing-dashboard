// Shared helpers for the Google OAuth (authorization-code) flow + signed session cookies.
// Server-side only (Cloudflare Pages Functions). No external deps; uses Web Crypto.

export function getCookie(request, name){
  const h = request.headers.get('Cookie') || '';
  const m = h.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'));
  return m ? decodeURIComponent(m[1]) : null;
}

export function base64urlEncode(str){
  const bytes = new TextEncoder().encode(str);
  let bin = ''; for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
export function base64urlDecodeToString(b64){
  const pad = b64.length % 4 === 0 ? '' : '='.repeat(4 - (b64.length % 4));
  const s = b64.replace(/-/g,'+').replace(/_/g,'/') + pad;
  const bin = atob(s);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

export async function hmacB64url(message, secret){
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name:'HMAC', hash:'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(message));
  const bytes = new Uint8Array(sig);
  let bin = ''; for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
export function timingSafeEqual(a, b){
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let out = 0; for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}

// Verify the signed session cookie -> returns the email, or null.
export async function verifySession(request, env){
  const cookie = getCookie(request, 'session');
  if (!cookie || !env.SESSION_SECRET) return null;
  const dot = cookie.lastIndexOf('.');
  if (dot < 1) return null;
  const payloadB64 = cookie.slice(0, dot), sig = cookie.slice(dot + 1);
  const expected = await hmacB64url(payloadB64, env.SESSION_SECRET);
  if (!timingSafeEqual(sig, expected)) return null;
  try {
    const p = JSON.parse(base64urlDecodeToString(payloadB64));
    if (!p.email || !p.exp || Date.now() > p.exp) return null;
    return p.email;
  } catch(e){ return null; }
}
export async function makeSession(email, secret, ttlMs){
  const payloadB64 = base64urlEncode(JSON.stringify({ email, exp: Date.now() + ttlMs }));
  const sig = await hmacB64url(payloadB64, secret);
  return payloadB64 + '.' + sig;
}

export function decodeJwtPayload(jwt){
  const parts = (jwt || '').split('.');
  if (parts.length < 2) return {};
  try { return JSON.parse(base64urlDecodeToString(parts[1])); } catch(e){ return {}; }
}
export function allowedDomains(env){
  return (env.ALLOWED_DOMAIN || 'ifit.com,iconfitness.com')
    .split(',').map(d => d.trim().toLowerCase()).filter(Boolean);
}
export function randomState(){
  const a = new Uint8Array(16); crypto.getRandomValues(a);
  let s = ''; for (const b of a) s += b.toString(16).padStart(2, '0'); return s;
}

// A minimal branded HTML response (used for the sign-in prompt / access-denied pages).
export function htmlMessage(title, msg, opts = {}){
  const signin = opts.signin ? `<a href="/auth/login" style="display:inline-block;margin-top:16px;padding:9px 20px;background:#78F264;color:#12313B;border-radius:999px;text-decoration:none;font-weight:700">Sign in with Google</a>` : '';
  const switchAcct = opts.switchAccount ? `<a href="/auth/logout" style="display:block;margin-top:18px;color:#BEB8A2;font-size:12px;text-decoration:none">Sign in with a different account</a>` : '';
  return new Response(
    `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title></head>`
    + `<body style="font-family:ui-sans-serif,system-ui,'Segoe UI',Roboto,sans-serif;background:#272930;color:#F2FEFF;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0">`
    + `<div style="max-width:460px;text-align:center;padding:40px">`
    + `<div style="font-weight:800;letter-spacing:-.02em;font-size:20px;margin-bottom:20px">iFIT · Marketing FP&amp;A</div>`
    + `<h1 style="font-size:22px;margin:0 0 12px;font-weight:700">${title}</h1>`
    + `<p style="color:#BEB8A2;line-height:1.6;font-size:14px;margin:0">${msg}</p>${signin}${switchAcct}`
    + `</div></body></html>`,
    { status: opts.status || 200, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } }
  );
}
