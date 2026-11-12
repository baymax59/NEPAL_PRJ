# The web interface (Step 14.1): built once with Node.js, then served by Caddy, which also passes
# /api requests on to the backend. The server itself needs no Node.js.
FROM node:24.19.0-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2.11.9-alpine
COPY --from=build /src/dist /srv/www
# The Caddy configuration is mounted from deploy/Caddyfile (see docker-compose.yml).
