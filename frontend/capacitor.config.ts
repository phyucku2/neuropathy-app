import type { CapacitorConfig } from '@capacitor/cli';

/**
 * Capacitor configuration (ADR-0023 — mobile via Capacitor, Android-first).
 *
 * The mobile app is the SAME SPA the web app ships (`webDir: 'dist'`, the `vite build`
 * output E2E already drives in a real browser). Capacitor wraps that bundle in a native
 * WebView shell; there is no second codebase.
 *
 * `appId` is the Android application id / Play Store package name. It becomes PERMANENT
 * once the app is first published to Google Play — CONFIRM IT BEFORE THE FIRST RELEASE.
 * Until then it is a free-to-change local identifier.
 *
 * `androidScheme: 'https'` serves the bundled app over an `https://localhost` origin
 * inside the WebView (Capacitor's default) — a secure context, so Web Crypto / secure
 * cookies / storage behave as on the web. No `server.url` is set: the app loads the
 * BUNDLED assets, never a remote dev server, in the shipped build (a dev-only live-reload
 * `server.url` is opt-in via an env-driven override, never committed).
 */
const config: CapacitorConfig = {
  appId: 'com.ahwg.neuropathy',
  appName: 'Neuropathy',
  webDir: 'dist',
  android: {
    // The WebView origin is https://localhost (secure context). Cleartext is off — the
    // app only talks to the API over TLS (runtime /config.js supplies the base URL).
    allowMixedContent: false,
  },
  plugins: {
    // The app hides the splash itself once React has mounted (useNativeShell), so the user
    // never sees a white flash between the native splash and the first paint (ADR-0025).
    SplashScreen: {
      launchAutoHide: false,
    },
  },
};

export default config;
