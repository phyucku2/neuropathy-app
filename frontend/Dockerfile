# syntax=docker/dockerfile:1
#
# Frontend image (ADR-0018). Stage 1 builds the SPA with Node 22; stage 2 serves the
# static output from a NON-ROOT nginx. No secrets are baked in — the API base URL is
# injected at container START via /config.js (runtime config), so ONE immutable image
# serves any environment without a rebuild.

# Pin to a specific minor tag; for production also pin by digest and bump deliberately.
FROM node:22-slim AS build

ENV CI=true
WORKDIR /app

# Dependency layer first for cache hits: install from the lockfile, then copy sources.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
FROM nginx:alpine AS runtime

# envsubst (from gettext) renders the nginx template at container start.
RUN apk add --no-cache gettext

# Serve the build output. Ownership goes to the stock non-root `nginx` user so the
# entrypoint can write /config.js into the web root at start time.
COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/nginx.conf.template
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && rm -f /etc/nginx/conf.d/default.conf

USER nginx

EXPOSE 8080

# Liveness: nginx's own /healthz (200), not the backend's.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
