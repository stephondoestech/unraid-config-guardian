<div align="center">

# Unraid Config Guardian

<img src="assets/unraid_guardian_logo.png" alt="Unraid Config Guardian Logo" width="200"/>

[![CI/CD Pipeline](https://github.com/stephondoestech/unraid-config-guardian/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/stephondoestech/unraid-config-guardian/actions/workflows/ci-cd.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/stephondoestech/unraid-config-guardian)](https://hub.docker.com/r/stephondoestech/unraid-config-guardian)
[![GitHub release](https://img.shields.io/github/release/stephondoestech/unraid-config-guardian.svg)](https://github.com/stephondoestech/unraid-config-guardian/releases)
[![License](https://img.shields.io/github/license/stephondoestech/unraid-config-guardian)](LICENSE)

**Your Unraid flash drive crashed and you don't have a backup?**

This tool saves you from complete disaster by automatically documenting your entire Unraid configuration.

</div>

## Flash Drive Disaster Recovery

**The Problem:** Your Unraid flash drive dies, taking with it:
- All Docker container configurations
- System settings and user shares
- Plugin configurations and templates
- Years of careful setup work

**The Solution:** Config Guardian automatically backs up everything needed to rebuild your server:
- **All running containers** → Docker templates + compose files
- **System configuration** → Settings, shares, plugins
- **Complete rebuild guide** → Step-by-step restoration
- **Change tracking** → See what changed between backups

## Application

<div align="center">

### Dashboard Overview
<img src="assets/demo_home.png" alt="Dashboard Screenshot" width="600"/>

### Container Management
<img src="assets/demo_containers.png" alt="Container Management Screenshot" width="600"/>

</div>



## Emergency Setup (Flash Drive Died)

### Quick Install on Fresh Unraid

1. **Install fresh Unraid** on new hardware/flash drive
2. **Set up basic array** and enable Docker
3. **Install Config Guardian:**

```bash
# SSH into Unraid and run:
mkdir -p /mnt/user/appdata/unraid-config-guardian
mkdir -p /mnt/user/backups/unraid-docs

docker run -d \
  --name unraid-config-guardian \
  --restart unless-stopped \
  -p 7842:7842 \
  -v /mnt/user/appdata/unraid-config-guardian:/config \
  -v /mnt/user/backups/unraid-docs:/output \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /boot:/boot:ro \
  -e PUID=99 -e PGID=100 \
  -e SCHEDULE="0 2 * * 0" \
  stephondoestech/unraid-config-guardian:latest
```

4. **Access:** `http://your-unraid-ip:7842`
5. **Generate backup** to start protecting your new setup

### Preventive Setup (Normal Use)

Install via **Community Apps** → Search "Config Guardian" → Install

**Pro Tip:** Set up weekly automated backups immediately after configuring any new containers!

## Your Backup Contains Everything Needed

```
unraid-backup/
├── container-templates.zip # Native Unraid XML templates → Drop in Docker tab
├── docker-compose.yml      # Emergency fallback containers
├── unraid-config.json      # System settings, shares, plugins
├── restore.sh              # Automated restoration script
├── changes.log             # What changed since last backup
└── README.md               # Step-by-step recovery guide
```

**Data Sources:**
- Running Docker containers (via Docker API)
- Unraid system configuration (`/boot/config/`)
- User shares and disk settings
- Plugin configurations and templates

## Super Simple Recovery

**When disaster strikes:**

1. **Fresh Unraid install** → Set up array
2. **Restore from backup:**
   ```bash
   cd /mnt/user/backups/unraid-docs/latest
   bash restore.sh
   ```
3. **Add containers:** Docker tab → Your templates are in the dropdown
4. **Copy back appdata** from your separate backups

**That's it!** Your entire server configuration is restored.

## IMPORTANT: This is NOT a Data Backup Solution

**Config Guardian only backs up your CONFIGURATION, not your data.** You still need a proper backup solution for your appdata and media files.

**Recommended backup solutions:**
- **Kopia** - Modern, fast, encrypted backups
- **Duplicacy** - Web-based backup management
- **Rustic** - Rust-based restic alternative
- **Unraid Plugins:** CA Backup/Restore, Appdata Backup

**What Config Guardian backs up:**
- Docker container configurations and templates
- Unraid system settings and shares
- Plugin configurations
- Recovery scripts and documentation

**What you still need to backup separately:**
- `/mnt/user/appdata/` (your container data)
- `/mnt/user/` (your media and files)
- Any custom scripts or configurations

## Configuration

**Essential Settings:**
```bash
SCHEDULE="0 2 * * 0"       # Weekly backup (Sunday 2 AM)
PUID=99 PGID=100           # Standard Unraid permissions
MASK_PASSWORDS=true        # Hide sensitive data in backups
```

**Common Issues:**
- **No templates in dropdown:** Enable Template Authoring Mode in Docker settings
- **Permission errors:** See [troubleshooting guide](docs/troubleshooting.md)

## Manual Usage

```bash
# Generate backup now
docker exec unraid-config-guardian python3 src/unraid_config_guardian.py

# View logs
docker logs unraid-config-guardian

# Check what changed
cat /mnt/user/backups/unraid-docs/latest/changes.log
```

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

**Built by [Stephon Parker](https://github.com/stephondoestech) for the Unraid community**

*Development supported by Claude (Anthropic)*

[⭐ Star](https://github.com/stephondoestech/unraid-config-guardian/stargazers) | [🐛 Issues](https://github.com/stephondoestech/unraid-config-guardian/issues) | [💡 Features](https://github.com/stephondoestech/unraid-config-guardian/issues)
