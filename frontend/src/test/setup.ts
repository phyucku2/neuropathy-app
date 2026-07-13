import { File as NodeFile } from 'node:buffer';
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest';
import { clearSession } from '../auth/tokenStore';
import { server } from './server';

// jsdom's File/FormData cannot be serialized by Node's fetch (undici): uploads
// hang or stringify. Node's own File and undici's FormData (recovered from the
// Response body parser, since Node does not export it) work end-to-end.
globalThis.File = NodeFile as unknown as typeof File;
const undiciForm = await new Response('probe=1', {
  headers: { 'content-type': 'application/x-www-form-urlencoded' },
}).formData();
globalThis.FormData = undiciForm.constructor as typeof FormData;

// recharts' ResponsiveContainer needs a ResizeObserver; jsdom has none.
class ResizeObserverStub {
  observe(): void {
    // no-op in jsdom
  }
  unobserve(): void {
    // no-op in jsdom
  }
  disconnect(): void {
    // no-op in jsdom
  }
}

globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

beforeEach(() => {
  clearSession();
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  sessionStorage.clear();
});

afterAll(() => {
  server.close();
});
