/**
 * Build-time constant injected by Vite's `define` (see vite.config.ts), sourced
 * from package.json `version`. Kept in this feature's own ambient declaration so
 * the About screen can show the shipped version without a runtime data call.
 */
declare const __APP_VERSION__: string;
