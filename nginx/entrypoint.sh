#!/bin/sh
# Substitute DOMAIN env var into nginx config
envsubst '${DOMAIN}' < /etc/nginx/templates/default.conf > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
