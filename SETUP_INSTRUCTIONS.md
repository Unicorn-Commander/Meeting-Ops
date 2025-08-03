# Meeting-Ops Setup Instructions

I've created a comprehensive setup script that will install everything needed for Meeting-Ops. Here's what to do:

## Step 1: Run the Setup Script

Open a terminal and run:

```bash
cd /home/ucadmin/Meeting-Ops
./setup_meeting_ops.sh
```

The script will:
- Install all system dependencies (PostgreSQL, Redis, Docker, etc.)
- Add your user to the `render` and `audio` groups for NPU access
- Set up the PostgreSQL database
- Create a Python virtual environment
- Install all Python packages
- Download the AI models
- Set up the frontend
- Create configuration files

## Step 2: Log Out and Log Back In

After the script completes, you MUST log out and log back in for the group permissions to take effect. This is required for NPU access.

## Step 3: Start the Services

After logging back in:

```bash
cd /home/ucadmin/Meeting-Ops
./start_all.sh
```

This will start:
- PostgreSQL database
- Qdrant vector database (via Docker)
- Backend API server on port 9050
- Frontend development server on port 7777

## Step 4: Access the Application

- Frontend: http://localhost:7777
- API Documentation: http://localhost:9050/docs
- Default credentials: `admin` / `admin123`

## Troubleshooting

If you encounter issues:

1. **NPU Access Denied**: Make sure you logged out and back in after running the setup
2. **Database Connection Failed**: Check PostgreSQL is running: `sudo systemctl status postgresql`
3. **Docker Issues**: Ensure Docker is running: `sudo systemctl status docker`
4. **Port Already in Use**: Check what's using the ports: `sudo netstat -tlnp | grep -E '7777|9050'`

## Manual Steps If Script Fails

If the automated script has issues, here are the key manual steps:

```bash
# 1. Add user to groups
sudo usermod -a -G render,audio,docker $USER

# 2. Fix NPU permissions
sudo chmod 666 /dev/accel/accel0

# 3. Create PostgreSQL database
sudo -u postgres psql
CREATE USER unicorn WITH PASSWORD 'commander';
CREATE DATABASE meeting_ops OWNER unicorn;
\q

# 4. Python setup
cd backend
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Frontend setup
cd ../frontend
npm install

# 6. Start services
cd ../backend
python main.py &
cd ../frontend
npm run dev -- --host 0.0.0.0 &
```

## Next Steps After Setup

1. **Test NPU**: Check if NPU acceleration is working properly
2. **Configure Email**: Edit `.env` file with your SMTP settings
3. **Test Recording**: Try recording a test session
4. **Check Transcription**: Verify live transcription is working
5. **Review Checklists**: Use the MASTER_CHECKLIST.md to verify all features

Let me know when you've run the setup script and logged back in!