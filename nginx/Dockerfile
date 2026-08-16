FROM nginx:1.27-alpine

RUN rm /etc/nginx/conf.d/default.conf

# Copy both dev and prod configs
COPY nginx.conf /etc/nginx/nginx.conf
COPY nginx.prod.conf /etc/nginx/nginx.prod.conf

# Create SSL directory
RUN mkdir -p /etc/nginx/ssl

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/health >/dev/null || exit 1
