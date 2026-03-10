# CortexDB Dashboard - Next.js
# Admin UI for CortexDB AI Agent Data Infrastructure
# (c) 2026 Nirlab Inc.

FROM node:20.11-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install

FROM node:20.11-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1

# Build-time API URL injection — pass via --build-arg or docker-compose
ARG NEXT_PUBLIC_API_URL=http://localhost:5400
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN npm run build

FROM node:20.11-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER nextjs

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost:3000/ || exit 1

EXPOSE 3000

CMD ["node", "server.js"]
