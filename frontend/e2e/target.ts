// The operator chooses the *frontend* origin. Never send a staff login to a
// default host, an API-only URL, or a public deployment by mistake.
function localOrigin(value: string | undefined): string {
  let url: URL | undefined;
  try { if (value) url = new URL(value); } catch { /* Do not echo the input. */ }
  if (!url || !['http:', 'https:'].includes(url.protocol) ||
      !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ||
      url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('Set E2E_BASE_URL to the HTTP(S) loopback origin serving the UI, without credentials, a path, query or fragment.');
  }
  return url.origin;
}

export const origin = localOrigin(process.env.E2E_BASE_URL);
