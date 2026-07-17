#!/bin/sh
# Frontend container entrypoint (ADR-0018): inject deploy-time runtime config and render
# the nginx config, then exec nginx in the foreground. Runs as the non-root nginx user.
set -eu

API_BASE_URL="${API_BASE_URL:-}"
: "${BACKEND_ORIGIN:=backend:8000}"

# 1. Runtime front-end config — one immutable image, per-environment API base, NO
#    rebuild. Empty means same-origin (nginx reverse-proxies the API). Contains no
#    secret: a public API base URL only.
printf 'window.__APP_CONFIG__ = { apiBaseUrl: "%s" };\n' "$API_BASE_URL" \
  >/usr/share/nginx/html/config.js

# 2. CSP connect-src: 'self' is always allowed; when the app talks to a cross-origin API
#    (API_BASE_URL set), that origin must also be allowed or the browser blocks it.
API_CONNECT_SRC="$API_BASE_URL"

# 2b. nginx DNS resolver for the variable proxy_pass. Auto-detect the container's own
#     nameserver so the same image works everywhere: 127.0.0.11 on Docker's embedded DNS,
#     the cluster DNS on Kubernetes / Azure Container Apps. Overridable via NGINX_RESOLVER;
#     falls back to Docker's 127.0.0.11 if resolv.conf can't be read.
NGINX_RESOLVER="${NGINX_RESOLVER:-$(awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf 2>/dev/null || true)}"
: "${NGINX_RESOLVER:=127.0.0.11}"
export BACKEND_ORIGIN API_CONNECT_SRC NGINX_RESOLVER

# 3. Temp paths for the non-root worker.
mkdir -p /tmp/nginx/client /tmp/nginx/proxy /tmp/nginx/fastcgi /tmp/nginx/uwsgi /tmp/nginx/scgi

# 4. Render the nginx config, substituting ONLY our whitelisted vars.
envsubst '${BACKEND_ORIGIN} ${API_CONNECT_SRC} ${NGINX_RESOLVER}' \
  </etc/nginx/templates/nginx.conf.template >/tmp/nginx.conf

exec nginx -c /tmp/nginx.conf -g 'daemon off;'
