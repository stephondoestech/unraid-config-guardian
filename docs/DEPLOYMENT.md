# Deployment Guide

## 🚀 CI/CD Pipeline Setup

### 1. GitHub Repository Setup

The repository now includes a complete CI/CD pipeline with:

```
.github/
├── workflows/
│   ├── ci-cd.yml          # Main CI/CD pipeline
│   └── release.yml        # Automatic releases
└── ISSUE_TEMPLATE/
    ├── bug_report.md      # Bug report template
    └── feature_request.md # Feature request template
```

### 2. Docker Hub Configuration

**Required GitHub Secrets:**

1. **Go to Repository Settings** → **Secrets and variables** → **Actions**
2. **Add these secrets:**

   ```
   DOCKER_USERNAME = your-dockerhub-username
   DOCKER_TOKEN    = your-dockerhub-access-token
   ```

**Creating Docker Hub Token:**
1. Login to [Docker Hub](https://hub.docker.com)
2. Go to **Account Settings** → **Security**
3. Click **New Access Token**
4. Name: `unraid-config-guardian-github`
5. Permissions: **Read, Write, Delete**
6. Copy the token and add it to GitHub secrets

### 3. Automated Workflows

The CI/CD pipeline automatically:

**On Pull Requests:**
- ✅ Runs tests (pytest)
- ✅ Code quality checks (black, flake8, mypy)
- ✅ Builds Docker image
- ✅ Security scanning (Trivy)

**On Push to `main`:**
- ✅ Everything above, plus:
- ✅ Deploys to Docker Hub as `latest`
- ✅ Multi-platform build (AMD64 + ARM64)

**On Version Tags (`v1.0.0`):**
- ✅ Everything above, plus:
- ✅ Creates GitHub Release
- ✅ Deploys versioned Docker image
- ✅ Updates Docker Hub description

### 4. Release Process

**Create a new release:**

```bash
# Make sure your changes are committed and pushed
git add .
git commit -m "Add: new feature description"
git push origin main

# Create and push a version tag
make tag VERSION=v1.0.0
```

**What happens automatically:**
1. GitHub Actions builds and tests
2. Multi-platform Docker image is created
3. Image is pushed to Docker Hub
4. GitHub Release is created with changelog
5. Unraid users can pull the new version

## 📦 Docker Hub Deployment

### Manual Deployment (if needed)

```bash
# Build for multiple platforms
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 \
  -t stephondoestech/unraid-config-guardian:latest \
  -t stephondoestech/unraid-config-guardian:v1.0.0 \
  --push .
```

### Image Tags Strategy

- **`latest`** - Latest stable release from main branch
- **`v1.0.0`** - Specific version tags
- **`main`** - Latest development from main branch
- **`develop`** - Development branch builds

## 🐳 Production Deployment

### Option 1: Docker Command (Unraid)

```bash
docker run -d \
  --name unraid-config-guardian \
  --restart unless-stopped \
  -p 7842:7842 \
  -v /mnt/user/appdata/unraid-config-guardian:/config \
  -v /mnt/user/backups/unraid-docs:/output \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /boot:/boot:ro \
  -e PUID=99 -e PGID=100 -e TZ=America/New_York \
  -e MASK_PASSWORDS=true \
  stephondoestech/unraid-config-guardian:latest
```

### Option 2: Docker Compose (Unraid)

```bash
# Copy docker-compose.yml to Unraid
scp docker-compose.yml root@unraid-server:/mnt/user/appdata/unraid-config-guardian/

# SSH into Unraid
ssh root@unraid-server
cd /mnt/user/appdata/unraid-config-guardian

# Deploy
docker-compose up -d
```

### Option 3: Unraid Community Apps

1. **Apps** → **Search** → "Config Guardian"
2. **Install** and configure paths
3. **Start** container

## 🔧 Environment Configuration

### Production Environment Variables

```bash
# Required
PUID=99                    # Unraid user ID
PGID=100                   # Unraid group ID
TZ=America/New_York        # Timezone

# Optional
SCHEDULE=0 2 * * 0         # Backup schedule (cron)
MASK_PASSWORDS=true        # Security
INCLUDE_SYSTEM_INFO=true   # System details
DEBUG=false                # Debug mode

# Advanced (optional)
WEBHOOK_URL=https://...    # Notifications
EMAIL_NOTIFICATIONS=admin@domain.com
WEB_HOST=0.0.0.0          # Web server host
WEB_PORT=8080             # Web server port
```

### Volume Mounts

```bash
# Required mounts
/mnt/user/appdata/unraid-config-guardian:/config      # App config
/mnt/user/backups/unraid-docs:/output                # Generated backups
/var/run/docker.sock:/var/run/docker.sock:ro         # Docker access
/boot:/boot:ro                                       # Unraid flash drive

# Optional mounts
/mnt/user:/mnt/user:ro                               # User shares
/etc/unraid:/etc/unraid:ro                           # System config
```

## 🌐 Accessing the Application

- **Web Interface**: `http://your-unraid-ip:7842`
- **Health Check**: `http://your-unraid-ip:7842/health` (coming soon)
- **API Endpoints**: `http://your-unraid-ip:7842/api/`

## 📊 Monitoring

### Container Health
```bash
# Check container status
docker ps | grep unraid-config-guardian

# View logs
docker logs unraid-config-guardian -f

# Health check
docker exec unraid-config-guardian python src/health_check.py
```

### Backup Verification
```bash
# Check generated files
ls -la /mnt/user/backups/unraid-docs/

# Verify backup content
cat /mnt/user/backups/unraid-docs/unraid-config.json | jq .
```

## 🔍 Troubleshooting

### Common Issues

**Container won't start:**
- Check Docker socket permissions
- Verify mount paths exist
- Check container logs: `docker logs unraid-config-guardian`

**No containers detected:**
- Verify Docker socket mount: `/var/run/docker.sock`
- Check PUID/PGID settings
- Ensure container has Docker access

**Web UI not accessible:**
- Check port mapping: `7842:7842`
- Verify firewall settings
- Check Unraid network configuration

**Backup generation fails:**
- Check output directory permissions
- Verify `/boot` mount is read-only
- Review container logs for errors

### Getting Help

1. **Check logs first**: `docker logs unraid-config-guardian`
2. **GitHub Issues**: Report bugs with logs and system info
3. **Unraid Forums**: Community support
4. **Discord**: Real-time help (coming soon)

## 📈 Scaling and Performance

### Resource Usage
- **Memory**: ~100-200MB typical usage
- **CPU**: Minimal (spikes during backup generation)
- **Disk**: Backup files typically 1-10MB each

### Optimization Tips
- Run backups during low-usage hours
- Use SSD for `/config` if frequent backups
- Adjust `SCHEDULE` based on server change frequency
- Monitor `/output` disk usage

## 🔒 Security Considerations

- Container runs as non-root user (guardian)
- Docker socket is read-only mounted
- Sensitive environment variables are masked
- No network privileges required
- Flash drive mounted read-only
- Security scanning included in CI/CD

---

**Ready to deploy!** 🚀 The application is now production-ready with complete CI/CD automation.
