# ─────────────────────────────────────────────────────────────────
# XF Internal Linker V2 — Angular Frontend Dockerfile (Dev)
# Node 22 (LTS) — matches latest Angular requirements
# ─────────────────────────────────────────────────────────────────

FROM node:22-slim

# Avoid 'npm install' issues in some environments
ENV CI=true
ENV CHROME_BIN=/usr/bin/chromium
ENV NODE_OPTIONS=--max-old-space-size=4096

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libu2f-udev \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for better caching
COPY package*.json ./
RUN npm install --legacy-peer-deps

# Copy the rest of the code
COPY . .

# Angular default dev port
EXPOSE 4200

# Start the dev server with host 0.0.0.0 so it's reachable from outside
CMD ["npm", "start", "--", "--host", "0.0.0.0"]
