# ────────────────────────────────
#  Build stage
# ────────────────────────────────
FROM node:20-bookworm AS builder
WORKDIR /app

# Copy lock-files FIRST
COPY package.json package-lock.json* pnpm-lock.yaml* yarn.lock* ./

# Copy the rest of the source code NEXT (respecting .dockerignore)
COPY . .

# Install dependencies AFTER copying source
RUN npm ci

# Build the application
RUN npm run build

# ────────────────────────────────
#  Runtime stage
# ────────────────────────────────
FROM gcr.io/distroless/nodejs20-debian12 AS runner
WORKDIR /app

# Copy only runtime essentials
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules

# Cloud Run listens on 8080 by convention
ENV PORT=8080
EXPOSE 8080

# `next start` automatically picks up PORT
CMD ["node_modules/next/dist/bin/next", "start", "-p", "8080"]