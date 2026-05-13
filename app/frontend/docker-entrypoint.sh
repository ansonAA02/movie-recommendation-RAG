#!/bin/sh
# English comment: Render the Nginx config template with runtime environment variables.
envsubst '${PORT} ${BACKEND_URL}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

# English comment: Start Nginx in the foreground for Docker.
exec nginx -g 'daemon off;'
