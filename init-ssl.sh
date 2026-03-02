set -e

DOMAIN=$1
EMAIL=$2

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "Usage: ./init-ssl.sh <domain> <email>"
    exit 1
fi

echo "==> Creating docker volumes..."
docker volume create certbot-webroot 2>/dev/null || true
docker volume create certbot-certs 2>/dev/null || true

echo "==> Starting nginx (HTTP only) for ACME challenge..."
docker run --rm -d --name nginx-init \
    -p 80:80 \
    -v "$(pwd)/nginx/default.conf:/etc/nginx/templates/default.conf:ro" \
    -v certbot-webroot:/var/www/certbot \
    -e DOMAIN="$DOMAIN" \
    nginx:alpine sh -c "
        envsubst '\${DOMAIN}' < /etc/nginx/templates/default.conf \
        | sed '/listen 443/,/^}/d' > /etc/nginx/conf.d/default.conf && \
        nginx -g 'daemon off;'
    "

echo "==> Waiting for nginx to start..."
sleep 3

echo "==> Requesting certificate from Let's Encrypt..."
docker run --rm \
    -v certbot-webroot:/var/www/certbot \
    -v certbot-certs:/etc/letsencrypt \
    certbot/certbot certonly \
        --webroot \
        --webroot-path /var/www/certbot \
        -d "$DOMAIN" \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email

echo "==> Stopping temporary nginx..."
docker stop nginx-init 2>/dev/null || true

echo "==> Done! Now run:"
echo "    DOMAIN=$DOMAIN docker compose up -d"
