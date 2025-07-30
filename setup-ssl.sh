#!/bin/bash

# setup-ssl.sh
# Automates Let's Encrypt certificate installation and Nginx configuration for HTTPS.

# --- Configuration Variables ---
DOMAIN="your_domain.com" # !!! IMPORTANT: Replace with your actual domain name !!!
EMAIL="your_email@example.com" # !!! IMPORTANT: Replace with your actual email for Let's Encrypt notifications !!!
NGINX_CONF_PATH="/etc/nginx/sites-available/unicorn-commander.conf"
NGINX_ENABLED_PATH="/etc/nginx/sites-enabled/unicorn-commander.conf"
APP_PORT=9050 # Port where your FastAPI backend is running
FRONTEND_PORT=7777 # Port where your React frontend is running

# --- Functions ---
log_info() { echo -e "\e[32m[INFO]\e[0m $1"; }
log_warn() { echo -e "\e[33m[WARN]\e[0m $1"; }
log_error() { echo -e "\e[31m[ERROR]\e[0m $1"; exit 1; }

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_error "This script must be run as root. Please use sudo."
    fi
}

install_certbot() {
    log_info "Installing Certbot and Nginx plugin..."
    if command -v apt &> /dev/null; then
        sudo apt update
        sudo apt install -y certbot python3-certbot-nginx
    elif command -v yum &> /dev/null; then
        sudo yum install -y epel-release
        sudo yum install -y certbot python3-certbot-nginx
    else
        log_error "Unsupported package manager. Please install Certbot manually."
    fi
    log_info "Certbot installed."
}

configure_nginx() {
    log_info "Configuring Nginx for SSL..."

    # Create Nginx configuration for Unicorn Commander
    cat <<EOF | sudo tee ${NGINX_CONF_PATH}
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/${DOMAIN}/chain.pem;

    # Modern SSL configuration
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;

    # Proxy to FastAPI backend
    location /api/ {
        proxy_pass http://127.0.0.1:${APP_PORT}/api/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        send_timeout 300s;
    }

    # Proxy to WebSocket for live transcription
    location /ws/ {
        proxy_pass http://127.0.0.1:${APP_PORT}/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400s; # Long timeout for websockets
        proxy_send_timeout 86400s;
    }

    # Serve React frontend static files
    location / {
        root /home/ucadmin/Development/Unicorn-Commander-Meeting-Ops/frontend/dist; # Assuming your React build output is in frontend/dist
        try_files \$uri \$uri/ /index.html;
    }

    # Optional: If you want to proxy the frontend through Nginx too, uncomment and adjust
    # location / {
    #     proxy_pass http://127.0.0.1:${FRONTEND_PORT};
    #     proxy_set_header Host \$host;
    #     proxy_set_header X-Real-IP \$remote_addr;
    #     proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    #     proxy_set_header X-Forwarded-Proto \$scheme;
    # }
}
EOF

    # Create symlink to enable the site
    if [ ! -L ${NGINX_ENABLED_PATH} ]; then
        sudo ln -s ${NGINX_CONF_PATH} ${NGINX_ENABLED_PATH}
        log_info "Nginx site enabled."
    else
        log_info "Nginx site already enabled."
    fi

    # Create webroot for certbot
    sudo mkdir -p /var/www/certbot
    sudo chown -R \$USER:\$USER /var/www/certbot

    log_info "Testing Nginx configuration..."
    sudo nginx -t || log_error "Nginx configuration test failed. Please check ${NGINX_CONF_PATH}"
    log_info "Reloading Nginx..."
    sudo systemctl reload nginx || log_error "Failed to reload Nginx."
    log_info "Nginx configured and reloaded."
}

request_certificate() {
    log_info "Requesting Let's Encrypt SSL certificate for ${DOMAIN}..."
    sudo certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos --email ${EMAIL}
    if [ \$? -ne 0 ]; then
        log_error "Certbot failed to obtain SSL certificate. Check logs for details."
    fi
    log_info "SSL certificate obtained and installed."
}

setup_renewal_cron() {
    log_info "Setting up Certbot renewal cron job..."
    # Certbot usually sets up a cron job or systemd timer automatically.
    # We'll just ensure it's there and working.
    if sudo systemctl list-timers | grep -q certbot.timer; then
        log_info "Certbot systemd timer found. Renewal will be handled automatically."
    else
        log_warn "Certbot systemd timer not found. Adding a basic cron job."
        (sudo crontab -l 2>/dev/null; echo "0 */12 * * * certbot renew --quiet") | sudo crontab -
        log_info "Cron job added for Certbot renewal."
    fi
}

# --- Main Script Execution ---
check_root

log_info "Starting SSL/HTTPS configuration for Unicorn Commander Meeting Ops."
log_warn "Please ensure your domain (${DOMAIN}) is pointing to this server's IP address."
log_warn "Also, ensure ports 80 and 443 are open on your firewall."

install_certbot
configure_nginx
request_certificate
setup_renewal_cron

log_info "SSL/HTTPS setup complete for ${DOMAIN}."
log_info "Your application should now be accessible via https://${DOMAIN}"
log_info "Remember to update your frontend's VITE_API_URL to use HTTPS if not already configured."

exit 0
