import { config } from '@agent-os/config';

type FetchOptions = RequestInit & {
  params?: Record<string, string | number | undefined>;
};

class APIClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  setToken(token: string) {
    this.token = token;
  }

  clearToken() {
    this.token = null;
  }

  private buildUrl(path: string, params?: Record<string, string | number | undefined>): string {
    const url = new URL(`${this.baseUrl}${path}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          url.searchParams.set(key, String(value));
        }
      });
    }
    return url.toString();
  }

  private async request<T>(path: string, options: FetchOptions = {}): Promise<T> {
    const { params, ...fetchOptions } = options;
    const url = this.buildUrl(path, params);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(url, {
      ...fetchOptions,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        title: 'Request failed',
        status: response.status,
        detail: response.statusText,
        error_code: 'request_failed',
      }));
      throw new APIError(error);
    }

    if (response.status === 204) return undefined as T;
    return response.json();
  }

  get<T>(path: string, params?: Record<string, string | number | undefined>) {
    return this.request<T>(path, { method: 'GET', params });
  }

  post<T>(path: string, body?: unknown) {
    return this.request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  put<T>(path: string, body?: unknown) {
    return this.request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  delete<T>(path: string) {
    return this.request<T>(path, { method: 'DELETE' });
  }

  sse(path: string, onEvent: (event: MessageEvent) => void, onError?: (error: Event) => void) {
    const url = this.buildUrl(path);
    const eventSource = new EventSource(url);
    eventSource.onmessage = onEvent;
    if (onError) eventSource.onerror = onError;
    return () => eventSource.close();
  }
}

export class APIError extends Error {
  status: number;
  errorCode: string;
  detail: string;

  constructor(problem: { title: string; status: number; detail: string; error_code: string }) {
    super(problem.title);
    this.status = problem.status;
    this.errorCode = problem.error_code;
    this.detail = problem.detail;
  }
}

export const api = new APIClient(config.api.baseUrl);
