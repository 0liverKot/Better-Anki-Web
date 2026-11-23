import { session } from './session.svelte';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public data: any,
  ) {
    super(message);
  }
}

interface Options {
  method?: string;
  body?: unknown;
  form?: FormData;
  keepalive?: boolean;
}

export async function api<T = any>(path: string, opts: Options = {}): Promise<T> {
  // The backend rejects writes without this header (CSRF protection).
  const headers: Record<string, string> = { 'X-Requested-With': 'baw' };
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }

  let res: Response;
  try {
    res = await fetch(path, {
      method: opts.method ?? (body !== undefined ? 'POST' : 'GET'),
      headers,
      body,
      credentials: 'same-origin',
      keepalive: opts.keepalive,
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection.", null);
  }

  const isJson = res.headers.get('content-type')?.includes('application/json');
  const data = isJson ? await res.json().catch(() => null) : null;
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/api/auth/')) {
      session.authenticated = false;
    }
    const detail = typeof data?.detail === 'string' ? data.detail : res.statusText;
    throw new ApiError(res.status, detail || `Request failed (${res.status})`, data);
  }
  return data as T;
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
