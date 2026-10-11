# ==============================================================================
# The Lenny Growth Assistant - Pi Coding Agent SDK Bridge Dockerfile
# Isolated Node.js daemon hosting @earendil-works/pi-coding-agent runtime
# ==============================================================================

FROM node:22-slim

WORKDIR /app

# Install curl for container healthcheck and network verification
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package specifications for optimal caching
COPY package.json package-lock.json ./
RUN npm ci

# Copy source code and models manifest
COPY . .

# Default service configuration (can be overridden via Docker Compose environment)
ENV PORT=8765 \
    HOST=0.0.0.0 \
    PI_AGENT_HOST=0.0.0.0 \
    PI_AGENT_PORT=8765 \
    OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
    PI_AGENT_MODEL=qwen2.5:1.5b \
    PI_AGENT_TIMEOUT_MS=180000

EXPOSE 8765

# Healthcheck probing /health via Node HTTP module (always available and dependency-free)
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
  CMD node -e "require('http').get('http://127.0.0.1:8765/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["npm", "start"]
