import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiBaseUrl } from './runtimeConfig';

describe('apiBaseUrl', () => {
  afterEach(() => {
    delete window.__APP_CONFIG__;
    vi.unstubAllEnvs();
  });

  it('prefers the runtime deploy-time config when present', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://build-time.example.org');
    window.__APP_CONFIG__ = { apiBaseUrl: 'https://runtime.example.org' };
    expect(apiBaseUrl()).toBe('https://runtime.example.org');
  });

  it('falls back to the build-time env when no runtime config is set', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://build-time.example.org');
    expect(apiBaseUrl()).toBe('https://build-time.example.org');
  });

  it('treats an empty runtime value as unset and falls through', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://build-time.example.org');
    window.__APP_CONFIG__ = { apiBaseUrl: '' };
    expect(apiBaseUrl()).toBe('https://build-time.example.org');
  });

  it('defaults to same-origin (empty string) when nothing is configured', () => {
    vi.stubEnv('VITE_API_BASE_URL', '');
    expect(apiBaseUrl()).toBe('');
  });
});
