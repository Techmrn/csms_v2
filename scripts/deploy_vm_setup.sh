#!/usr/bin/env bash
# ==============================================================================
# CSMS V2 - Google Cloud Compute Engine e2-micro VM Setup Script
# Target OS: Debian 12 (Bookworm)
# ==============================================================================
set -euo pipefail

echo "============================================================"
echo " Starting CSMS V2 e2-micro VM Setup"
echo "============================================================"

# 1. Update system packages
echo "[1/4] Updating base system packages..."
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y git curl htop ca-certificates gnupg

# 2. Configure 2.5 GB Swap File to prevent Out-Of-Memory (OOM) crashes
echo "[2/4] Checking and configuring Swap space..."
if [ ! -f /swapfile ]; then
    echo "Creating 2.5 GB swap file at /swapfile..."
    sudo fallocate -l 2.5G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2560
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "Swap created successfully."
else
    echo "Swapfile already exists. Skipping creation."
fi

# Set swappiness to 20 to prioritize RAM and use swap only for safety buffers
sudo sysctl vm.swappiness=20
if ! grep -q "vm.swappiness=20" /etc/sysctl.conf; then
    echo 'vm.swappiness=20' | sudo tee -a /etc/sysctl.conf
fi

# 3. Install Docker Engine and Docker Compose Plugin
echo "[3/4] Installing Docker and Docker Compose..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    sudo usermod -aG docker "$USER"
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "Docker installed successfully."
else
    echo "Docker is already installed."
fi

# 4. Summary & next steps
echo "============================================================"
echo " Setup complete!"
echo " Free memory and swap status:"
free -h
echo "============================================================"
echo "NEXT STEPS:"
echo "1. If you just installed Docker, log out and log back in (or run 'newgrp docker') so group permissions take effect."
echo "2. Clone this repo: git clone https://github.com/Techmrn/csms_v2.git"
echo "3. cd csms_v2"
echo "4. cp .env.production.example .env && nano .env"
echo "5. docker compose run --rm app alembic upgrade head"
echo "6. docker compose up -d"
echo "============================================================"
