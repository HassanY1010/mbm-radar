# MBM Radar - Free Deployment Guide (Direct Python / Non-Docker Setup)

This guide explains how to deploy **MBM Radar** directly using native Python setups (without Docker) on Render.com or on a private VPS.

---

## 1. Free Deployment on Render.com (Direct Python)

If you do not want to use Docker, Render supports running Python Web Services natively:

1. **Upload your code**: Ensure the `requirements.txt` file exists in the root folder and is pushed to GitHub.
2. **Create Render Web Service**: Go to Render, click **New** -> **Web Service**, and connect your repository.
3. **Configure Settings**:
   - **Environment/Language**: Select **Python** (instead of Docker).
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. **Environment Variables**: Add your database, redis connection, bot token, channel ID, and API keys as environment variables in the settings panel (same as Docker).
5. **Start Deployment**: Render will install python libraries natively, download packages, and run the uvicorn start command.

---

## 2. Direct VPS Deployment (Native Linux systemd Service)

If you are deploying on a private Ubuntu/Debian Cloud VPS without Docker:

### Step 1: Install Python and Packages
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

### Step 2: Clone and Setup Environment
```bash
git clone <your-repository-url> /opt/mbm_radar
cd /opt/mbm_radar
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and enter your database connection details, bot tokens, and api keys
nano .env
```

### Step 3: Configure System Service (systemd)
To ensure the scanner, bot, and API run 24/7 in the background and auto-restart upon server reboot:

1. Create a systemd service file:
   ```bash
   sudo nano /etc/systemd/system/mbm_radar.service
   ```
2. Paste the following configuration:
   ```ini
   [Unit]
   Description=MBM Radar Application Service
   After=network.target

   [Service]
   User=root
   WorkingDirectory=/opt/mbm_radar
   ExecStart=/opt/mbm_radar/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
   Restart=always
   RestartSec=5
   EnvironmentFile=/opt/mbm_radar/.env

   [Install]
   WantedBy=multi-user.target
   ```
3. Enable and start the background service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable mbm_radar
   sudo systemctl start mbm_radar
   ```
4. Monitor logs in real-time:
   ```bash
   sudo journalctl -u mbm_radar -f
   ```
