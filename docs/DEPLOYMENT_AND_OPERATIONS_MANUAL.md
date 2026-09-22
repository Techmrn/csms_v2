# CSMS V2 — Deployment, Architecture & Operations Manual

This document serves as the authoritative operational manual for the **Central Store Management System V2 (CSMS V2)** hosted on Google Cloud Platform (Compute Engine) with a remote Supabase PostgreSQL database under a strict **$0.00 / Zero-Cost** architecture.

---

## 1. System Architecture & Infrastructure Specifications

| Component | Specification | Purpose / Notes |
| :--- | :--- | :--- |
| **Cloud Provider** | Google Cloud Platform (GCP) | Free Tier eligible |
| **Compute Instance** | `instance-20260921-040032` | Non-preemptible `e2-micro` (2 shared vCPU, 1 GB RAM) |
| **GCP Zone** | `us-central1-c` (Council Bluffs, Iowa, USA) | Mandatory for GCP Always-Free compute coverage |
| **Operating System** | Debian 12 (Bookworm) 64-bit | Clean minimal Linux distribution |
| **Boot Disk** | Standard Persistent Disk (`pd-standard`) $\le 30$ GB | Free tier rule: Must be `pd-standard`, not SSD/balanced |
| **Virtual Memory** | 2.5 GB Swapfile (`/swapfile`) | Prevents Linux OOM (Out-of-Memory) kernel kills |
| **Swappiness** | `vm.swappiness = 10` | Keeps RAM prioritized; uses swap only under pressure |
| **Container Engine** | Docker Community Edition (Docker CE) + Compose | Isolated, reproducible container runtime |
| **Application Server** | Uvicorn ASGI (`--workers 1`) | Single-process event loop; avoids RAM multiplication |
| **Database** | Supabase PostgreSQL (Free Tier) | Hosted in AWS `us-east-1` (N. Virginia, USA) |
| **Network Latency** | ~25–35 ms (Iowa $\leftrightarrow$ Virginia) | Low round-trip database query latency |

---

## 2. Firewall & Networking Configuration

### Inbound Firewall Rules (Google Cloud VPC)

To allow public access without a domain/SSL setup:

| Rule Name | Direction | Action | Source IP Range | Protocols & Ports | Target |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `allow-csms-web` | Ingress | Allow | `0.0.0.0/0` | TCP `80`, `8000` | All instances in the network |

- **Port 80 (`http://<IP>/`)**: Primary web port; maps directly to container port `8000`.
- **Port 8000 (`http://<IP>:8000/`)**: Secondary access port; maps directly to container port `8000`.

---

## 3. How to Obtain the Public / External IP Address

### Method A: From Inside the VM (Command Line)
Run either of these commands in your SSH terminal:
```bash
curl -4 ifconfig.me
```
or
```bash
curl -s https://api.ipify.org
```
*(Example output: `34.133.4.30`)*

### Method B: From the Google Cloud Console
1. Navigate to: **Compute Engine > VM instances**.
2. Locate `instance-20260921-040032`.
3. Read the IP under the **External IP** column.
4. Access in your browser using **plain HTTP**:
   - `http://<EXTERNAL_IP>` (Port 80)
   - `http://<EXTERNAL_IP>:8000` (Port 8000)

> [!WARNING]
> **Use `http://`, NOT `https://`**:
> Because direct IP connections do not have an SSL certificate, entering `https://` will trigger an `ERR_SSL_PROTOCOL_ERROR`. Always specify `http://`.

---

## 4. Environment Variables Reference (`.env`)

Located on the VM at `/home/maheshrnair007/csms_v2/.env`:

| Variable | Type | Example / Description |
| :--- | :--- | :--- |
| `APP_NAME` | String | `"CSMS V2"` |
| `DEBUG` | Boolean | `False` *(Must be False in production to disable verbose disk I/O logging)* |
| `DATABASE_URL` | String | `"postgresql+asyncpg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres"` |
| `JWT_SECRET_KEY` | Hex / String | 32-byte cryptographically secure random string (generated via `openssl rand -hex 32`) |
| `JWT_ALGORITHM` | String | `"HS256"` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Integer | `480` (8 hours session validity) |

### Important Rules for `DATABASE_URL`:
- **Driver prefix**: Must start with `postgresql+asyncpg://`.
- **Port**:
  - `5432`: **Session Pooler mode** (Recommended for long-lived application connections).
  - `6543`: **Transaction Pooler mode** (PgBouncer).
- **Region**: Must match the US location (`aws-0-us-east-1.pooler.supabase.com`) to avoid cross-continental network latency.
- Do NOT append `?pgbouncer=true` (that parameter is Prisma-specific; our code handles PgBouncer statement caches automatically).

---

## 5. Seeded System Accounts Reference

All accounts were seeded with the password: **`Password@1`**

| Username | Role Code | Role Description | Assigned Office / Store Scope |
| :--- | :--- | :--- | :--- |
| **`dev_admin`** | `SYSTEM_ADMIN` | System Administrator | Master Administration & Organization Management |
| **`dev_director`** | `DIRECTOR` | Director / Superintendent | Directorate Oversight & Approvals |
| **`dev_deputy`** | `DEPUTY_SUPDT_STORES` | Deputy Superintendent, Stock & Stores | Central Store Controlling Officer |
| **`dev_general_sk`** | `GENERAL_STOREKEEPER` | General Storekeeper | Central Store Stock Operations & Registers |
| **`dev_assistant_sk`**| `ASSISTANT_STOREKEEPER` | Assistant Storekeeper | Central Store Stock Entry & Operations |
| **`dev_press_head`** | `BRANCH_HEAD` | Central Press Branch Head | Central Press Office Approvals |
| **`dev_press_sk`** | `BRANCH_STOREKEEPER` | Central Press Storekeeper | Central Press Store Stock Operations |

---

## 6. Standard Operating Procedures (SOP) for Updates & Maintenance

All commands are executed from the project root on the VM:
```bash
cd /home/maheshrnair007/csms_v2
```

### Protocol 1: Deploying Code Updates from GitHub
Whenever you push changes from your development computer to GitHub:

```bash
# 1. Pull the latest commits
git pull origin main

# 2. If new database migrations were added, run them:
docker compose run --rm app alembic upgrade head

# 3. Rebuild and restart the container cleanly:
docker compose up -d --build

# 4. Confirm container health:
docker compose ps
docker compose logs -f
```

---

### Protocol 2: Modifying Environment Variables (`.env`)
> [!IMPORTANT]
> `docker compose restart app` does **NOT** reload `.env`! Docker requires recreating the container:

```bash
# 1. Edit .env
nano .env

# 2. Recreate container with the updated variables
docker compose down && docker compose up -d
```

---

### Protocol 3: Running Database Seeds or Diagnostic Scripts
Always run Python maintenance scripts inside the container using one-off commands or interactive bash:

```bash
# Interactive bash session inside the container:
docker compose run --rm -it app bash

# Inside the shell:
python scripts/seed.py
python scripts/seed_dev_users.py
exit
```

---

### Protocol 4: Routine Health & Monitoring Checks

1. **View Live Application Logs (with response times)**:
   ```bash
   docker compose logs -f app
   ```
2. **Check Memory and Swap Usage**:
   ```bash
   free -h
   ```
3. **Monitor Container Resource Consumption**:
   ```bash
   docker stats csms_app
   ```
4. **Restart Application Container**:
   ```bash
   docker compose restart app
   ```
5. **Stop Application (Clean Shutdown)**:
   ```bash
   docker compose down
   ```

---

## 7. Troubleshooting Guide

| Symptom | Probable Cause | Corrective Action |
| :--- | :--- | :--- |
| **`ERR_CONNECTION_TIMED_OUT`** | GCP VPC Firewall is dropping packets | Ensure the `allow-csms-web` firewall rule allows ports `80` and `8000` to `0.0.0.0/0`. |
| **`ERR_SSL_PROTOCOL_ERROR`** | Typed `https://` instead of `http://` | Direct IP has no TLS certificate. Navigate to `http://<IP>:8000/` or use an Incognito window. |
| **`Child process died` in a loop** | OOM killer terminating multi-worker Python | Ensure `Dockerfile` runs with `--workers 1` and `mem_limit` is omitted from `docker-compose.yml`. |
| **Website pages take 3–5 seconds** | Cross-continental DB latency or verbose SQL logs | 1. Ensure Supabase is located in `us-east-1`.<br>2. Ensure `DEBUG=False` in `.env`.<br>3. Run `docker compose down && docker compose up -d` to verify `.env` is loaded. |
| **`unexpected character "+"` in `.env`** | Missing `DATABASE_URL=` key on line 11 | Open `nano .env` and ensure line starts with `DATABASE_URL="postgresql+asyncpg://..."`. |
