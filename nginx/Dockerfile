# ============================================================
# CortexDB - Nginx Reverse Proxy
# TLS termination, rate limiting, security headers
# (c) 2026 Nirlab Inc. All Rights Reserved.
# ============================================================

FROM nginx:alpine

LABEL maintainer="Nirlab Inc <eng@nirlab.ai>"
LABEL description="CortexDB Nginx reverse proxy with TLS termination"

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Copy CortexDB nginx configuration
COPY nginx.conf /etc/nginx/conf.d/cortexdb.conf

# Create directories for SSL certs, ACME challenges, and custom error pages
RUN mkdir -p /etc/nginx/ssl /var/www/certbot

# Add a simple 50x error page
RUN echo '<!DOCTYPE html><html><head><title>CortexDB - Service Unavailable</title></head><body style="font-family:sans-serif;text-align:center;padding:50px"><h1>Service Temporarily Unavailable</h1><p>CortexDB is starting up or temporarily unavailable. Please try again shortly.</p></body></html>' > /usr/share/nginx/html/50x.html

EXPOSE 80 443

HEALTHCHECK --interval=10s --timeout=3s --retries=3 --start-period=5s \
    CMD wget -qO /dev/null http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
