// GET /auth/logout — clear the session cookie and bounce to a fresh sign-in.
export const onRequestGet = async (context) => {
  const url = new URL(context.request.url);
  const headers = new Headers({ 'Location': url.origin + '/auth/login' });
  headers.append('Set-Cookie', `session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`);
  return new Response(null, { status: 302, headers });
};
