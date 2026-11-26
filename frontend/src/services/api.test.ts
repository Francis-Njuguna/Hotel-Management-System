import { afterEach, expect, it, vi } from 'vitest';
import { api, send } from './api';

afterEach(() => vi.unstubAllGlobals());
it('keeps tender precision and CSRF on same-origin writes', async () => {
  document.cookie = 'csrftoken=demo-token; path=/';
  const fetcher = vi.fn().mockResolvedValue(new Response('{}',{headers:{'content-type':'application/json'}}));
  vi.stubGlobal('fetch',fetcher);
  await send('invoices/8/payments/','POST',{amount:'850.25',reference:'TEST-ONLY'});
  const [url,opts] = fetcher.mock.calls[0];
  expect(url.pathname).toBe('/api/v1/invoices/8/payments/');
  expect(opts.credentials).toBe('same-origin'); expect(opts.headers.get('X-CSRFToken')).toBe('demo-token');
  expect(JSON.parse(opts.body).amount).toBe('850.25');
});
it('surfaces field errors rather than treating a rejected write as success', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({departure:['Must follow arrival.']}),{status:400,headers:{'content-type':'application/json'}})));
  await expect(api('reservations/')).rejects.toThrow('departure: Must follow arrival.');
});
