# English comment: Build the Vite frontend in a small Node image.
FROM node:18-alpine AS build

# English comment: Keep the frontend build rooted at /app.
WORKDIR /app

# English comment: Copy dependency manifests first for better Docker caching.
COPY package*.json ./

# English comment: Install exact frontend dependencies.
RUN npm ci

# English comment: Copy the application source before the production build.
COPY . .

# English comment: Build the static assets for the Nginx runtime stage.
RUN npm run build

# English comment: Serve the built SPA through Nginx with runtime env substitution.
FROM nginx:1.27-alpine

# English comment: Install envsubst so Railway runtime variables can be injected into Nginx config.
RUN apk add --no-cache gettext

# English comment: Provide safe defaults for local Docker Compose and Railway.
ENV PORT=80 \
    BACKEND_URL=http://backend:8000

# English comment: Copy the built app and the runtime Nginx template files.
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh

# English comment: Allow the custom entrypoint to render config and start Nginx.
RUN chmod +x /docker-entrypoint.sh

# English comment: Railway still probes the runtime PORT even if EXPOSE is informational only.
EXPOSE 80

# English comment: Start Nginx with the generated config.
CMD ["/docker-entrypoint.sh"]
