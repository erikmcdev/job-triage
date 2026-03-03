set -e

DOMAIN=$1
EMAIL=$2

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "Usage: ./init-ssl.sh <domain> <email>"
    exit 1
fi

# Use the same volume names that docker-compose creates
WEBROOT_VOL="job-triage_certbot-webroot"
CERTS_VOL="job-triage_certbot-certs"

echo "==> Creating docker volumes..."
docker volume create "$WEBROOT_VOL" 2>/dev/null || true
docker volume create "$CERTS_VOL" 2>/dev/null || true

echo "==> Starting nginx (HTTP only) for ACME challenge..."
docker run --rm -d --name nginx-init \
    -p 80:80 \
    -v "$(pwd)/nginx/init.conf:/etc/nginx/conf.d/default.conf:ro" \
    -v "$WEBROOT_VOL":/var/www/certbot \
    nginx:alpine

echo "==> Waiting for nginx to start..."
sleep 3

echo "==> Requesting certificate from Let's Encrypt..."
docker run --rm \
    -v "$WEBROOT_VOL":/var/www/certbot \
    -v "$CERTS_VOL":/etc/letsencrypt \
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
