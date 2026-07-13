/**
 * Typed fetch client — the single place for the API base URL, the Authorization
 * header, and the refresh-on-401-once retry (ADR-0015).
 *
 * Every response error becomes an ApiError carrying the backend's `detail`
 * string, so screens can show friendly, specific messages. Tokens and PHI are
 * never logged.
 */

import type { AccessTokenOut } from './types';
import {
  getAccessToken,
  getRefreshToken,
  notifySessionExpired,
  setAccessToken,
} from '../auth/tokenStore';

export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';

/** Absolute URL for an API path (same-origin by default; VITE_API_BASE_URL overrides). */
function apiUrl(path: string): string {
  return new URL(`${API_BASE_URL}${path}`, window.location.origin).toString();
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  /** JSON body — serialized with the right content type. */
  body?: unknown;
  /** Multipart body — sent as-is (the browser sets the boundary). */
  formData?: FormData;
  /** Skip the Authorization header + refresh retry (auth endpoints). */
  anonymous?: boolean;
}

const GENERIC_DETAIL = 'Something went wrong. Please try again.';

async function errorDetail(response: Response): Promise<string> {
  try {
    const payload: unknown = await response.json();
    if (payload !== null && typeof payload === 'object' && 'detail' in payload) {
      const detail = (payload as { detail: unknown }).detail;
      if (typeof detail === 'string') {
        return detail;
      }
    }
  } catch {
    // Non-JSON error body — fall through to the generic message.
  }
  return GENERIC_DETAIL;
}

function buildInit(options: RequestOptions, token: string | null): RequestInit {
  const headers = new Headers();
  let body: BodyInit | undefined;
  if (options.formData !== undefined) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(options.body);
  }
  if (token !== null && !options.anonymous) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return { method: options.method ?? 'GET', headers, body };
}

/** Single-flight refresh: concurrent 401s share one POST /auth/refresh. */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (refreshToken === null) {
    notifySessionExpired();
    return false;
  }
  const response = await fetch(apiUrl('/auth/refresh'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    notifySessionExpired();
    return false;
  }
  const tokens = (await response.json()) as AccessTokenOut;
  setAccessToken(tokens.access_token);
  return true;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await fetch(apiUrl(path), buildInit(options, getAccessToken()));

  // One refresh-and-retry per request, never more (ADR-0015).
  if (response.status === 401 && !options.anonymous) {
    refreshInFlight ??= refreshAccessToken().finally(() => {
      refreshInFlight = null;
    });
    const refreshed = await refreshInFlight;
    if (refreshed) {
      response = await fetch(apiUrl(path), buildInit(options, getAccessToken()));
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await errorDetail(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** The user-facing message for any thrown value — ApiError detail or a generic line. */
export function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  return GENERIC_DETAIL;
}
