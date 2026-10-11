# ==============================================================================
# The Lenny Growth Assistant - Frontend Production Dockerfile
# Multi-stage build: compiles Vite/React bundle, then serves via lightweight Nginx
# ==============================================================================

# Stage 1: Build production bundle
FROM node:20-alpine AS build
WORKDIR /app

# Copy dependency manifests first for layer caching
COPY package.json package-lock.json ./
RUN npm ci

# Copy application source code
COPY . .

# Build production bundle into /app/dist
RUN npm run build

# Stage 2: Production web server
FROM nginx:alpine
WORKDIR /usr/share/nginx/html

# Remove default Nginx welcome page
RUN rm -rf ./*

# Copy built artifacts from Stage 1
COPY --from=build /app/dist .

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
