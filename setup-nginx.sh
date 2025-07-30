#!/bin/bash

# Unicorn Commander Meeting Ops - Single Port Nginx Setup
# This script configures nginx to serve both frontend and backend on port 80

set -e

echo "🚀 Setting up Unicorn Commander single-port access with Nginx..."

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "Please don't run this script as root. It will use sudo when needed."
   exit 1
fi

# Check if nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "📦 Installing nginx..."
    sudo apt update
    sudo apt install -y nginx
else
    echo "✅ Nginx is already installed"
fi

# Create directories
echo "📁 Creating directories..."
sudo mkdir -p /opt/unicorn-commander/{frontend,nginx,logs}
sudo mkdir -p /var/log/nginx

# Build frontend if not already built
echo "🏗️  Building frontend..."
cd frontend
if [ ! -d "dist" ]; then
    echo "   Building React frontend..."
    npm install
    npm run build
else
    echo "   Frontend already built"
fi

# Copy frontend build to production directory
echo "📋 Copying frontend files..."
sudo cp -r dist/* /opt/unicorn-commander/frontend/
sudo chown -R www-data:www-data /opt/unicorn-commander/frontend

# Copy nginx configuration
echo "⚙️  Installing nginx configuration..."
sudo cp ../nginx.conf /opt/unicorn-commander/nginx/nginx.conf
sudo chown root:root /opt/unicorn-commander/nginx/nginx.conf

# Test nginx configuration
echo "🧪 Testing nginx configuration..."
sudo nginx -t -c /opt/unicorn-commander/nginx/nginx.conf

# Stop default nginx if running
echo "🛑 Stopping default nginx..."
sudo systemctl stop nginx 2>/dev/null || true

# Install and start systemd service
echo "🔧 Installing systemd service..."
sudo cp ../systemd/unicorn-commander-nginx.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable unicorn-commander-nginx.service

# Start nginx service
echo "▶️  Starting nginx service..."
sudo systemctl start unicorn-commander-nginx.service
sudo systemctl status unicorn-commander-nginx.service --no-pager

# Check if port 80 is available
echo "🔍 Checking port 80..."
if sudo netstat -tlnp | grep -q :80; then
    echo "✅ Nginx is listening on port 80"
else
    echo "❌ Port 80 is not listening. Check logs:"
    sudo journalctl -u unicorn-commander-nginx.service --no-pager -n 20
    exit 1
fi

# Create firewall rules if ufw is active
if command -v ufw &> /dev/null && sudo ufw status | grep -q "Status: active"; then
    echo "🔥 Configuring firewall..."
    sudo ufw allow 80/tcp comment 'Unicorn Commander HTTP'
    sudo ufw allow 443/tcp comment 'Unicorn Commander HTTPS (future)'
    echo "   Firewall rules added for ports 80 and 443"
fi

# Test the setup
echo "🧪 Testing the setup..."
sleep 2

# Test frontend
if curl -s -o /dev/null -w "%{http_code}" http://localhost/ | grep -q "200"; then
    echo "✅ Frontend is accessible on http://localhost/"
else
    echo "⚠️  Frontend test failed, but this might be expected if backend isn't running"
fi

# Test API (if backend is running)
if curl -s -o /dev/null -w "%{http_code}" http://localhost/api/status | grep -q "200"; then
    echo "✅ Backend API is accessible on http://localhost/api/"
else
    echo "⚠️  Backend API test failed - make sure backend is running on port 9050"
fi

echo ""
echo "🎉 Single-port nginx setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Make sure your backend is running on port 9050:"
echo "      cd backend && python -m uvicorn main_docker:app --host 0.0.0.0 --port 9050"
echo ""
echo "   2. Access the application:"
echo "      Frontend: http://localhost/"
echo "      API: http://localhost/api/"
echo "      WebSocket: ws://localhost/ws/"
echo ""
echo "   3. For HTTPS, configure SSL certificates and uncomment the HTTPS section in nginx.conf"
echo ""
echo "📝 Service management:"
echo "   Start:   sudo systemctl start unicorn-commander-nginx.service"
echo "   Stop:    sudo systemctl stop unicorn-commander-nginx.service"
echo "   Restart: sudo systemctl restart unicorn-commander-nginx.service"
echo "   Status:  sudo systemctl status unicorn-commander-nginx.service"
echo "   Logs:    sudo journalctl -u unicorn-commander-nginx.service -f"
echo ""
echo "📊 Monitoring:"
echo "   Access logs: /var/log/nginx/unicorn-access.log"
echo "   Error logs:  /var/log/nginx/unicorn-error.log"
echo "   Health check: http://localhost/health"