# Frontend Dockerfile

# Build stage
FROM node:20-alpine as builder

# Vite reads VITE_*-prefixed env vars at build time and inlines them into
# the bundle. Declare ARG + ENV so docker-compose build-args reach the npm
# script. Without this the bundle falls through to the runtime same-origin
# default in src/config.ts.
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

# v3.19 polished launch: when "true", `/` renders the public invite-only
# Landing page (`pages/Landing.tsx`) for anonymous visitors. Default
# stays "false" so existing dev deploys keep the historical
# `/` → `/dashboard` redirect. Authenticated users always go to
# /dashboard regardless of this flag.
ARG VITE_LANDING_PAGE_ENABLED=false
ENV VITE_LANDING_PAGE_ENABLED=$VITE_LANDING_PAGE_ENABLED

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application. build:docker now runs `tsc -b && vite build`
# (parity with `npm run build`), so a strict TypeScript error fails the
# Docker build instead of silently riding to production as it did before
# (17 strict errors + at least one real runtime bug in
# AdminBulkImport.tsx where showToast was called as a function instead
# of showToast.error(...) snuck through for weeks).
RUN npm run build:docker

# Production stage
FROM nginx:alpine

# Copy built files to nginx
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 7777

# Start nginx
CMD ["nginx", "-g", "daemon off;"]