# Browser Access Guide for Meeting-Ops

## The Problem
When accessing the Meeting-Ops frontend via IP address (e.g., `192.168.1.145:7777`), some browsers or extensions may incorrectly add "www." prefix, resulting in `www.192.168.1.145:7777` which doesn't work.

## Solutions

### 1. **Use Full URL with Protocol** (Recommended)
Always include `http://` when typing the URL:
```
http://192.168.1.145:7777
```

### 2. **Use Localhost** (If on Same Machine)
```
http://localhost:7777
```

### 3. **Add Trailing Slash**
```
http://192.168.1.145:7777/
```

### 4. **Browser-Specific Fixes**

#### Chrome/Edge
- Disable "Use a web service to help resolve navigation errors" in settings
- Check for extensions that might be modifying URLs

#### Firefox
- Type `about:config` in address bar
- Search for `browser.fixup.alternate.enabled`
- Set it to `false`

#### Safari
- Preferences → Search → Uncheck "Include search engine suggestions"
- Preferences → Search → Uncheck "Preload top hit in background"

### 5. **Permanent Fix - Host File Entry**
Add to `/etc/hosts` (Linux/Mac) or `C:\Windows\System32\drivers\etc\hosts` (Windows):
```
192.168.1.145 meeting-ops.local
```
Then access via:
```
http://meeting-ops.local:7777
```

### 6. **Check Browser Extensions**
Disable extensions that might interfere:
- URL shorteners
- Security extensions
- VPN extensions
- Ad blockers (temporarily)

### 7. **Clear Browser Data**
1. Clear cache and cookies for the IP address
2. Clear DNS cache:
   - Windows: `ipconfig /flushdns`
   - Linux: `sudo systemd-resolve --flush-caches`
   - Mac: `sudo dscacheutil -flushcache`

## What We've Fixed in Code

1. **Frontend Auto-Fix**: The app now detects and removes incorrect "www." prefixes
2. **Clean URL Handling**: All API calls use cleaned URLs without www. prefix
3. **WebSocket Connections**: Fixed to use proper IP addresses

## Testing Access

Try these in order:
1. `http://192.168.1.145:7777`
2. `http://192.168.1.145:7777/login`
3. `http://localhost:7777` (if local)
4. `curl http://192.168.1.145:7777` (command line test)

## If Still Having Issues

1. **Check if frontend is running**:
   ```bash
   netstat -tlnp | grep 7777
   ```

2. **Check firewall**:
   ```bash
   sudo ufw status
   ```

3. **Try different browser or incognito mode**

4. **Check nginx (if using)**:
   ```bash
   sudo nginx -t
   sudo systemctl status nginx
   ```

## Network Troubleshooting

From the client machine:
```bash
# Test connectivity
ping 192.168.1.145

# Test port
nc -zv 192.168.1.145 7777

# Test HTTP
curl -I http://192.168.1.145:7777
```

## Alternative Access Methods

1. **SSH Tunnel** (if you have SSH access):
   ```bash
   ssh -L 7777:localhost:7777 ucadmin@192.168.1.145
   ```
   Then access: `http://localhost:7777`

2. **Use Backend API Directly**:
   ```
   http://192.168.1.145:9050/docs
   ```