# Microphone Access Guide for Meeting-Ops

## Quick Solutions

### Option 1: Use localhost (Easiest)
Access the app via `http://localhost:7777` instead of IP address:
```bash
cd frontend
npm run dev:localhost
```
Then open: http://localhost:7777

### Option 2: Setup HTTPS (Recommended for Network Access)
```bash
cd frontend
npm run setup:https  # Generate certificates
npm run dev:https     # Start with HTTPS
```
Then open: https://YOUR_IP:7777 (accept certificate warning)

### Option 3: Chrome Flags (For Testing)
Start Chrome with special flag:
```bash
# Linux
google-chrome --unsafely-treat-insecure-origin-as-secure="http://YOUR_IP:7777" --user-data-dir=/tmp/chrome-test

# Example for 192.168.1.145
google-chrome --unsafely-treat-insecure-origin-as-secure="http://192.168.1.145:7777" --user-data-dir=/tmp/chrome-test
```

## Why This Is Needed

Modern browsers require HTTPS for accessing sensitive APIs like:
- Microphone (getUserMedia)
- Camera
- Geolocation
- etc.

Exception: `localhost` and `127.0.0.1` are considered secure contexts.

## Production Deployment

For production, use a proper SSL certificate with nginx:
```bash
# Use the included nginx configuration
cd /home/ucadmin/Meeting-Ops
./setup-nginx.sh
```

This sets up:
- Proper SSL with Let's Encrypt
- Reverse proxy to backend
- WebSocket support
- Security headers

## Troubleshooting

### "Not Allowed Error"
- Click the lock/info icon in address bar
- Go to Site Settings
- Allow Microphone access

### "Not Found Error"
- Check if microphone is connected
- Check system settings:
  ```bash
  # List audio devices
  arecord -l
  
  # Test microphone
  arecord -d 5 test.wav && aplay test.wav
  ```

### "Not Readable Error"
- Close other apps using the microphone
- Check PulseAudio:
  ```bash
  pactl list sources
  ```

## Browser Compatibility

| Browser | localhost | HTTPS | HTTP+Flag |
|---------|-----------|-------|-----------|
| Chrome  | ✅ | ✅ | ✅ |
| Firefox | ✅ | ✅ | ❌ |
| Safari  | ✅ | ✅ | ❌ |
| Edge    | ✅ | ✅ | ✅ |

## Security Note

For a local-only system (air-gapped):
- Option 1 (localhost) is perfectly fine
- Self-signed HTTPS is acceptable
- No external SSL certificate needed

For internet-facing systems:
- Always use proper SSL certificates
- Consider using nginx with Let's Encrypt
- Enable security headers