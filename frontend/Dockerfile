# syntax=docker/dockerfile:1.7
# Build context: repository root (compose: context ".", dockerfile "frontend/Dockerfile").
# Builds the three SPAs once (one build serves every tenant) and serves them with Caddy.
FROM node:24-alpine AS build
RUN corepack enable
WORKDIR /src
COPY frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/package.json ./
COPY frontend/packages/ui/package.json packages/ui/
COPY frontend/packages/api-client/package.json packages/api-client/
COPY frontend/apps/tenant/package.json apps/tenant/
COPY frontend/apps/platform/package.json apps/platform/
COPY frontend/apps/site/package.json apps/site/
RUN pnpm install --frozen-lockfile
COPY frontend/ .
RUN pnpm build

FROM caddy:2-alpine
COPY --from=build /src/apps/tenant/dist /srv/tenant
COPY --from=build /src/apps/platform/dist /srv/platform
COPY --from=build /src/apps/site/dist /srv/site
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
EXPOSE 8080
