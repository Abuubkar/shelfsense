# The storefront as a Next.js standalone server. Build from the repo root:
#   docker build -f apps/web/Dockerfile .
# The proxy target for /api/* is fixed at build time (Next writes rewrites into the build), so SHELFSENSE_API is a
# build argument; the default fits a compose network with a service called `api`. Server-rendered pages read the
# same variable at run time.

FROM node:24-slim AS build
RUN npm install --global pnpm@11.15.0
WORKDIR /web
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
ARG SHELFSENSE_API=http://api:8020
ENV SHELFSENSE_API=$SHELFSENSE_API NEXT_TELEMETRY_DISABLED=1
RUN pnpm build


FROM node:24-slim AS runtime
ARG SHELFSENSE_API=http://api:8020
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3020 HOSTNAME=0.0.0.0 SHELFSENSE_API=$SHELFSENSE_API
WORKDIR /web
COPY --from=build --chown=node /web/.next/standalone ./
COPY --from=build --chown=node /web/.next/static ./.next/static
USER node
EXPOSE 3020
CMD ["node", "server.js"]
