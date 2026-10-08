import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { graphqlBaseQuery } from './api';

const apiContext = { signal: new AbortController().signal, dispatch: vi.fn(), getState: () => ({}) };
const NativeRequest = globalThis.Request;

beforeEach(() => vi.stubGlobal('Request', class extends NativeRequest {
  constructor(input, init) {
    super(typeof input === 'string' ? new URL(input, 'http://localhost:5173') : input, init);
  }
}));

afterEach(() => vi.unstubAllGlobals());

describe('GraphQL transport', () => {
  it('maps session failures to an actionable authentication state', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      errors: [{ message: 'Sign in to continue' }],
    }), { headers: { 'content-type': 'application/json' } })));

    const result = await graphqlBaseQuery({ query: '{ viewer { id } }' }, apiContext, {});

    expect(result.error).toEqual({ status: 401, message: 'Sign in to continue' });
  });

  it('returns successful typed data without GraphQL wrapping', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      data: { viewer: { name: 'Asha' } },
    }), { headers: { 'content-type': 'application/json' } })));

    const result = await graphqlBaseQuery({ query: '{ viewer { name } }' }, apiContext, {});

    expect(result.data.viewer.name).toBe('Asha');
  });

  it('rotates an expired access session and retries the original GraphQL query once', async () => {
    let graphqlRequests = 0;
    const fetchMock = vi.fn(async (request) => {
      if (request.url.endsWith('/auth/refresh')) return new Response(null, { status: 204 });
      graphqlRequests += 1;
      if (graphqlRequests === 1) {
        return new Response(JSON.stringify({ errors: [{ message: 'Sign in to continue' }] }), {
          headers: { 'content-type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ data: { viewer: { id: 'u1' } } }), {
        headers: { 'content-type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await graphqlBaseQuery({ query: '{ viewer { id } }' }, apiContext, {});

    expect(result.data.viewer.id).toBe('u1');
    expect(graphqlRequests).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('coalesces concurrent access-expiry refreshes into one rotation', async () => {
    let refreshRequests = 0;
    const fetchMock = vi.fn(async (request) => {
      if (request.url.endsWith('/auth/refresh')) {
        refreshRequests += 1;
        await Promise.resolve();
        return new Response(null, { status: 204 });
      }
      if (refreshRequests === 0) {
        return new Response(JSON.stringify({ errors: [{ message: 'Sign in to continue' }] }), {
          headers: { 'content-type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ data: { viewer: { id: 'u1' } } }), {
        headers: { 'content-type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const results = await Promise.all([
      graphqlBaseQuery({ query: '{ viewer { id } }' }, apiContext, {}),
      graphqlBaseQuery({ query: '{ viewer { id } }' }, apiContext, {}),
    ]);

    expect(results.map((result) => result.data.viewer.id)).toEqual(['u1', 'u1']);
    expect(refreshRequests).toBe(1);
  });
});