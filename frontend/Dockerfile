# ─────────────────────────────────────────────────────────────────
# XF Internal Linker V2 — Angular Frontend Dockerfile (Dev)
# Node 22 (LTS) — matches latest Angular requirements
# ─────────────────────────────────────────────────────────────────

FROM node:22-slim

# Avoid 'npm install' issues in some environments
ENV CI=true

WORKDIR /app

# Install dependencies first for better caching
COPY package*.json ./
RUN npm install

# Copy the rest of the code
COPY . .

# Angular default dev port
EXPOSE 4200

# Start the dev server with host 0.0.0.0 so it's reachable from outside
CMD ["npm", "start", "--", "--host", "0.0.0.0"]
