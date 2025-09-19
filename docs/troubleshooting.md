# Troubleshooting Guide

## Permission Issues

### Problem: Container fails to write backup files

**Symptoms:**
- "Permission denied" errors in container logs
- Backup files not appearing in output directory
- Container exits with permission errors

**Root Cause:**
Mismatch between container user permissions and host directory ownership. The container runs as a specific user ID internally but needs to match your Unraid system's user permissions.

### Solutions

#### 1. Set Correct PUID/PGID (Recommended)

The container supports Unraid's standard PUID/PGID environment variables:

```bash
# Standard Unraid user/group
PUID=99    # 'nobody' user ID
PGID=100   # 'users' group ID

# Or use your custom user ID
PUID=1000  # Your user ID
PGID=1000  # Your group ID
```

**Docker run example:**
```bash
docker run -d \
  --name unraid-config-guardian \
  -e PUID=99 -e PGID=100 \
  -v /mnt/user/backups/unraid-docs:/output \
  stephondoestech/unraid-config-guardian:latest
```

#### 2. Fix Output Directory Permissions

If permission errors persist, check and fix directory ownership:

```bash
# SSH into Unraid and check current permissions
ls -la /mnt/user/backups/unraid-docs

# Set correct ownership (use your PUID/PGID values)
chown -R 99:100 /mnt/user/backups/unraid-docs

# Verify permissions are set correctly
ls -la /mnt/user/backups/unraid-docs
```

#### 3. Debug Container User Setup

Verify the container is using the correct user:

```bash
# Check what user the container is running as
docker exec unraid-config-guardian id

# Check container logs for user setup messages
docker logs unraid-config-guardian | grep "Setting up user"

# Expected output should show:
# Setting up user permissions: PUID=99, PGID=100
# User setup complete: guardian user now has UID=99, GID=100
```

### Common Permission Scenarios

| Scenario | PUID/PGID | Directory Owner | Result |
|----------|-----------|-----------------|--------|
| Standard Unraid | 99/100 | 99:100 | ✅ Works |
| Custom user | 1000/1000 | 1000:1000 | ✅ Works |
| No PUID/PGID set | Default (1000/1000) | 99:100 | ❌ Permission denied |
| Wrong ownership | 99/100 | root:root | ❌ Permission denied |

### Quick Fix Commands

```bash
# For standard Unraid setup (99:100)
chown -R 99:100 /mnt/user/backups/unraid-docs

# For custom user (replace with your IDs)
chown -R 1000:1000 /mnt/user/backups/unraid-docs

# Check if container can write to directory
docker exec unraid-config-guardian touch /output/test.txt
docker exec unraid-config-guardian ls -la /output/test.txt
docker exec unraid-config-guardian rm /output/test.txt
```

## Container Startup Issues

### Problem: Container exits immediately

**Check container logs:**
```bash
docker logs unraid-config-guardian
```

**Common causes:**
- Missing required volume mounts (`/var/run/docker.sock`, `/boot`)
- Permission issues with mounted directories
- Invalid environment variables

### Problem: Web interface not accessible

**Verify port mapping:**
```bash
docker ps | grep unraid-config-guardian
```

**Check if port 7842 is available:**
```bash
netstat -tlnp | grep 7842
```

## Docker Socket Issues

### Problem: "Cannot connect to Docker daemon"

**Symptoms:**
- Container cannot list other containers
- Docker API errors in logs

**Solution:**
Ensure Docker socket is properly mounted:
```bash
-v /var/run/docker.sock:/var/run/docker.sock:ro
```

**Verify mount is working:**
```bash
docker exec unraid-config-guardian ls -la /var/run/docker.sock
```

## Boot Configuration Access

### Problem: Cannot read Unraid boot configuration

**Symptoms:**
- Missing system configuration in backup
- Errors about `/boot` directory access

**Solution:**
Ensure boot directory is mounted read-only:
```bash
-v /boot:/boot:ro
```

**Verify mount:**
```bash
docker exec unraid-config-guardian ls -la /boot/config
```

## Getting Help

If you're still experiencing issues:

1. **Collect logs:**
   ```bash
   docker logs unraid-config-guardian > guardian-logs.txt
   ```

2. **Check container status:**
   ```bash
   docker ps -a | grep unraid-config-guardian
   docker inspect unraid-config-guardian
   ```

3. **Open an issue:** [GitHub Issues](https://github.com/stephondoestech/unraid-config-guardian/issues)
   - Include logs and container configuration
   - Specify your Unraid version and setup details
