FROM node:20-slim AS builder
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@latest --activate
COPY backend/package.json backend/pnpm-lock.yaml ./backend/
WORKDIR /app/backend
RUN pnpm install --frozen-lockfile --ignore-scripts

COPY backend/ ./
RUN pnpm run build


FROM python:3.12-slim


RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY lego_core/requirements.txt /app/lego_core/requirements.txt
RUN pip install --no-cache-dir -r /app/lego_core/requirements.txt

COPY lego_core/ /app/lego_core/


WORKDIR /app/backend
COPY backend/package.json ./
RUN npm install --omit=dev

COPY --from=builder /app/backend/dist ./dist


RUN mkdir -p /app/.forma_storage

ENV NODE_ENV=production
ENV PORT=4000
ENV QUEUE_DRIVER=redis
ENV AUTO_START_WORKER=true

EXPOSE 4000

CMD ["node", "dist/index.js"]
