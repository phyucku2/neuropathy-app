import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  // `public/` holds static assets served verbatim (e.g. the runtime config.js shim,
  // ADR-0018), not part of the TypeScript program — excluded from linting. `android/`
  // is the generated Capacitor native project (Java/Gradle/XML + the copied web bundle
  // under assets/public); it is not TypeScript source and must not be linted (ADR-0023).
  {
    ignores: [
      'dist',
      'coverage',
      'node_modules',
      'public',
      'playwright-report',
      'test-results',
      'android',
      // Node build tooling (store-asset generators): console output and process.exit are
      // their job; they are not part of the browser app's TS program (ADR-0026 assets).
      'scripts',
      // Demo capture tooling (Playwright capture spec + HTML generator): Node/test globals
      // and console output are their job; not part of the browser app's TS program. The
      // captured PNGs and generated HTML live outside src and are not linted.
      'demo',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.strict,
  jsxA11y.flatConfigs.recommended,
  {
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
      // Tokens and PHI must never reach the console (CLAUDE.md §5 / ADR-0015).
      'no-console': 'error',
    },
  },
  prettier,
);
