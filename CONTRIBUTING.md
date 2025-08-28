# Contributing to Unraid Config Guardian

Thank you for your interest in contributing! This guide will help you get started.

## 🚀 Quick Development Setup

```bash
# Clone the repository
git clone https://github.com/stephondoestech/unraid-config-guardian.git
cd unraid-config-guardian

# Set up development environment
make dev-setup
source venv/bin/activate
make install-dev

# Run tests and quality checks
make check

# Start development server
make run-gui  # Web GUI at http://localhost:8080
# OR
make run      # CLI version
```

## 🧪 Testing

### Local Testing
```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest tests/test_unraid_config_guardian.py -v

# Run linting and type checking
make lint
make type-check
make format
```

### Docker Testing
```bash
# Build and test locally
make docker-build
make docker-dev

# Access at http://localhost:7842
```

## 📋 Development Workflow

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes:**
   - Write tests for new functionality
   - Follow existing code style
   - Update documentation if needed

3. **Test your changes:**
   ```bash
   make check  # Runs all quality checks
   ```

4. **Commit and push:**
   ```bash
   git add .
   git commit -m "Add: description of your changes"
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request:**
   - Use the PR template
   - Link any related issues
   - Ensure all CI checks pass

## 🎯 Areas for Contribution

### High Priority
- **Container Detection**: Improve container analysis and edge cases
- **Backup Formats**: Add support for other backup formats (Kubernetes YAML, etc.)
- **Notifications**: Implement email/webhook notifications
- **Scheduling**: Enhance cron scheduling with more options
- **Testing**: Expand test coverage, especially integration tests

### Medium Priority
- **UI Improvements**: Enhance the web interface
- **Documentation**: Better user guides and API docs
- **Performance**: Optimize for servers with many containers
- **Plugins**: Support for Unraid plugin backup

### Good First Issues
- **Bug Fixes**: Check GitHub issues labeled `good first issue`
- **Documentation**: Improve README, add examples
- **Templates**: Create more Unraid Community App templates
- **Testing**: Add unit tests for specific functions

## 🏗️ Architecture Overview

```
src/
├── unraid_config_guardian.py  # Main CLI application
├── web_gui.py                 # Production web interface
├── web_gui_dev.py            # Development web interface with mocks
└── health_check.py           # Container health monitoring

templates/                    # HTML templates for web UI
├── base.html                # Base template
├── dashboard.html           # Main dashboard
├── containers.html          # Container overview
└── backups.html            # Backup management

docker/
└── entrypoint.sh           # Container entrypoint script
```

## 🎨 Code Style Guidelines

### Python Code
- **Black** for formatting: `make format`
- **Flake8** for linting: `make lint`
- **MyPy** for type checking: `make type-check`
- **Line length**: 88 characters (Black default)
- **Type hints**: Required for all functions
- **Docstrings**: Google-style docstrings for all public functions

### Example:
```python
def process_container(container: Dict[str, Any]) -> ContainerInfo:
    """Process a Docker container and extract configuration.
    
    Args:
        container: Raw Docker container data
        
    Returns:
        ContainerInfo object with parsed configuration
        
    Raises:
        ValueError: If container data is invalid
    """
    # Implementation here
```

### Web Templates
- **Bootstrap 5** for styling
- **Semantic HTML** structure
- **Accessibility** considerations (ARIA labels, etc.)
- **Mobile-responsive** design

## 🔄 CI/CD Pipeline

Our GitHub Actions workflow:

1. **Test Stage**: Runs tests, linting, type checking
2. **Build Stage**: Builds Docker image for multiple platforms
3. **Security Stage**: Vulnerability scanning with Trivy
4. **Deploy Stage**: Pushes to Docker Hub (main branch & tags)

### Running CI Locally
```bash
# Run the same checks as CI
make check

# Build multi-platform (requires Docker Buildx)
make ci-build

# Test Docker image
make docker-build
make docker-dev
```

## 📦 Release Process

### Creating a Release

1. **Update version numbers** in relevant files
2. **Update CHANGELOG.md** with new features/fixes
3. **Create and push a tag:**
   ```bash
   make tag VERSION=v1.2.0
   ```
4. **GitHub Actions** will automatically:
   - Run full test suite
   - Build multi-platform Docker images
   - Push to Docker Hub
   - Create GitHub release

### Version Numbering
We follow [Semantic Versioning](https://semver.org/):
- `v1.0.0` - Major release (breaking changes)
- `v1.1.0` - Minor release (new features)
- `v1.1.1` - Patch release (bug fixes)

## 🐛 Bug Reports

When reporting bugs, please include:
- Unraid version
- Container/application version
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs
- Screenshots (for UI issues)

## 💡 Feature Requests

For new features:
- Describe the use case
- Explain why it would be valuable
- Consider implementation complexity
- Provide mockups for UI changes

## 🔒 Security

For security issues:
- **DO NOT** open public GitHub issues
- Email: security@stephondoestech.com
- Include details about the vulnerability
- Allow reasonable time for fixes before disclosure

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## 🙋‍♂️ Questions?

- **GitHub Discussions**: For general questions
- **GitHub Issues**: For bug reports and feature requests
- **Discord**: [Join our community](https://discord.gg/unraid-config-guardian) (coming soon)

Thank you for contributing to Unraid Config Guardian! 🎉