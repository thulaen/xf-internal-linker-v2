FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first for layer caching
COPY package*.json ./
RUN npm ci

# Copy source files
COPY . .

# Build the static site
RUN npm run build

# Serve via lightweight nginx
FROM nginx:alpine

# Copy built assets
COPY --from=builder /app/build /usr/share/nginx/html

# Expose port 80 inside container (mapped to 3000 externally)
EXPOSE 80
