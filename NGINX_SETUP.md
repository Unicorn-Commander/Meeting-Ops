# Unicorn Commander - Single Port Access Setup

This setup configures nginx to serve both the frontend and backend on a single port (80) for production deployment.

## Quick Setup

1. **Run the automated setup script:**
   ```bash
   ./setup-nginx.sh
   ```

2. **Start your backend server:**
   ```bash
   cd backend
   python -m uvicorn main_docker:app --host 0.0.0.0 --port 9050
   ```

3. **Access the application:**
   - Frontend: http://localhost/
   - API: http://localhost/api/
   - WebSocket: ws://localhost/ws/

## What the Setup Does

### 1. Installs and Configures Nginx
- Installs nginx if not already present
- Creates production directory structure at `/opt/unicorn-commander/`
- Configures nginx to serve on port 80

### 2. Frontend Setup
- Builds the React frontend (`npm run build`)
- Copies built files to `/opt/unicorn-commander/frontend/`
- Configures SPA routing with fallback to `index.html`

### 3. Backend Proxy
- Proxies `/api/*` requests to backend on port 9050
- Includes rate limiting for security
- Configures WebSocket support for `/ws/*`

### 4. Security Features
- Rate limiting on API endpoints (10 req/s) and auth endpoints (5 req/s)
- Security headers (X-Frame-Options, X-XSS-Protection, etc.)
- Blocks common exploit attempts
- Request size limits for file uploads

### 5. Performance Optimizations
- Gzip compression for text content
- Static asset caching (1 year for immutable assets)
- Connection keep-alive
- Upstream connection pooling

## Configuration Files

- **nginx.conf**: Main nginx configuration with single-port setup
- **systemd/unicorn-commander-nginx.service**: Systemd service for nginx
- **setup-nginx.sh**: Automated installation script

## Service Management

```bash
# Start nginx service
sudo systemctl start unicorn-commander-nginx.service

# Stop nginx service
sudo systemctl stop unicorn-commander-nginx.service

# Restart nginx service
sudo systemctl restart unicorn-commander-nginx.service

# Check status
sudo systemctl status unicorn-commander-nginx.service

# View logs
sudo journalctl -u unicorn-commander-nginx.service -f
```

## Log Files

- **Access logs**: `/var/log/nginx/unicorn-access.log`
- **Error logs**: `/var/log/nginx/unicorn-error.log`
- **Service logs**: `sudo journalctl -u unicorn-commander-nginx.service`

## Testing the Setup

### Health Check
```bash
curl http://localhost/health
# Should return: healthy
```

### Frontend Test
```bash
curl -I http://localhost/
# Should return: HTTP/1.1 200 OK
```

### API Test
```bash
curl http://localhost/api/status
# Should return JSON status if backend is running
```

### WebSocket Test
```bash
# Use browser console or WebSocket testing tool
new WebSocket('ws://localhost/ws/audio-levels')
```

## HTTPS Setup (Future)

To enable HTTPS (port 443):

1. **Obtain SSL certificates:**
   ```bash
   # Using Let's Encrypt (recommended)
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   
   # Or place your certificates at:
   # /etc/ssl/certs/unicorn-commander.crt
   # /etc/ssl/private/unicorn-commander.key
   ```

2. **Uncomment HTTPS section in nginx.conf**
3. **Restart nginx service**

## Troubleshooting

### Port 80 Already in Use
```bash
# Check what's using port 80
sudo netstat -tlnp | grep :80

# Stop default nginx if running
sudo systemctl stop nginx

# Or change the port in nginx.conf if needed
```

### Permission Issues
```bash
# Ensure proper ownership
sudo chown -R www-data:www-data /opt/unicorn-commander/frontend/
sudo chown root:root /opt/unicorn-commander/nginx/nginx.conf
```

### Backend Connection Issues
- Ensure backend is running on port 9050
- Check backend logs for errors
- Verify firewall allows internal connections

### Frontend Not Loading
- Check if frontend was built: `ls frontend/dist/`
- Verify files copied: `ls /opt/unicorn-commander/frontend/`
- Check nginx error logs

## Firewall Configuration

If using UFW:
```bash
sudo ufw allow 80/tcp comment 'Unicorn Commander HTTP'
sudo ufw allow 443/tcp comment 'Unicorn Commander HTTPS'
```

For production deployment, consider:
- Blocking unused ports
- Restricting SSH access
- Setting up fail2ban for additional security

## Performance Monitoring

Monitor nginx performance:
```bash
# Check connections
sudo ss -tuln | grep :80

# Monitor access logs
sudo tail -f /var/log/nginx/unicorn-access.log

# Check nginx status
curl http://localhost/health
```

## Directory Structure

```
/opt/unicorn-commander/
├── frontend/           # Built React app files
│   ├── index.html
│   ├── assets/
│   └── ...
├── nginx/
│   └── nginx.conf     # Production nginx config
└── logs/              # Application logs (if needed)
```

This setup provides a production-ready single-port configuration suitable for deployment on servers or embedded systems.