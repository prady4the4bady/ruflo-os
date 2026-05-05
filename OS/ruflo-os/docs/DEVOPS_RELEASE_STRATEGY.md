# NemOS DevOps, Packaging & Release Strategy#

## Executive Summary#

NemOS uses modern DevOps practices for reliable, repeatable builds and releases.

## Development Workflow#

### Branch Strategy#

```
main (stable)"
├── develop (integration)"
│   ├── feature/agent-runtime"
│   ├── feature/desktop-shell"
│   ├── bugfix/policy-engine"
│   └── release/v1.0.x"
```

### Commit Convention#

```
feat(agent): add reflection agent"
fix(desktop): resolve compositor crash"
docs(api): update OpenAPI spec"
test(orchestration): add DAG workflow tests"
refactor(core): simplify model router"
```

## Build System#

### Makefile Targets#

```makefile#
.PHONY: all test clean package release"

all: kernel packages desktop api"

kernel:"
\t$(MAKE) -C kernel/modules/ai_bridge"
\t$(MAKE) -C kernel/modules/ruflo_input"

packages:"
\tpip install -r requirements.txt"
\tpip install -e nemoclaw/"
\tpip install -e ruflo-agent/"
\tpip install -e hermes-integration/"
\tpip install -e api/"

desktop:"
\tcd ruflo-shell/compositor && meson setup build && cd build && ninja"

api:"
\tcd api && uvicorn ruflo_api_server:app --host 0.0.0.0 --port 8080 &"

test: unit integration e2e"

unit:"
\tpytest tests/unit/ -v --cov=."

integration:"
\tpytest tests/integration/ -v"

e2e:"
\tpytest tests/e2e/ -v --timeout=120"

clean:"
\trm -rf build/ dist/ *.egg-info/"
\tfind . -name "__pycache__" -exec rm -rf {} +"
\tfind . -name "*.pyc" -delete"
```

### Docker Multi-stage Builds#

```dockerfile#
# Dockerfile.multi-stage"
FROM python:3.12-slim as builder"

WORKDIR /build"
COPY requirements.txt ."
RUN pip wheel --no-deps -r requirements.txt"

COPY nemoclaw/ /app/nemoclaw/"
COPY ruflo-agent/ /app/ruflo-agent/"
COPY hermes-integration/ /app/hermes/"
COPY api/ /app/api/"

RUN pip wheel --no-deps -e /app/nemoclaw"
RUN pip wheel --no-deps -e /app/ruflo-agent"
RUN pip wheel --no-deps -e /app/hermes/"
RUN pip wheel --no-deps -e /app/api"

FROM python:3.12-slim"
COPY --from=builder /build/*.whl /tmp/"
RUN pip install /tmp/*.whl && rm /tmp/*.whl"

COPY --from=builder /app /app/"
WORKDIR /app"

EXPOSE 8080 8001 8002"
CMD ["uvicorn", "api.ruflo_api_server:app", "--host", "0.0.0.0"]"
```

## Continuous Integration#

### GitHub Actions Workflows#

```yaml#
# .github/workflows/ci.yml"
name: NemOS CI"

on: [push, pull_request]"

jobs:"
  lint:"
    runs-on: ubuntu-latest"
    steps:"
      - uses: actions/checkout@v4"
      - name: Run ruff"
        run: pip install ruff && ruff check ."
      - name: Run mypy"
        run: pip install mypy && mypy nemoclaw ruflo-agent hermes-integration api"

  test-unit:"
    runs-on: ubuntu-latest"
    steps:"
      - uses: actions/checkout@v4"
      - name: Run unit tests"
        run: pip install -r requirements.txt && pytest tests/unit/ -v --cov=."

  test-integration:"
    runs-on: ubuntu-latest"
    services:"
      postgres:"
        image: postgres:15"
        env:"
          POSTGRES_PASSWORD: test"
    steps:"
      - uses: actions/checkout@v4"
      - name: Run integration tests"
        run: |"
          pip install -r requirements.txt"
          pytest tests/integration/ -v --timeout=60"

  build-docker:"
    runs-on: ubuntu-latest"
    steps:"
      - uses: actions/checkout@v4"
      - name: Build Docker images"
        run: |"
          docker build -f docker/Dockerfile.nemoclaw -t nemos-nemoclaw ."
          docker build -f docker/Dockerfile.ruflo-agent -t nemos-ruflo-agent ."
          docker build -f docker/Dockerfile.hermes -t nemos-hermes ."
          docker build -f docker/Dockerfile.api -t nemos-api ."
```

### Release Workflow#

```yaml#
# .github/workflows/release.yml"
name: NemOS Release"

on:"
  push:"
    tags: ['v*']"

jobs:"
  release:"
    runs-on: ubuntu-latest"
    steps:"
      - uses: actions/checkout@v4"

      - name: Build packages"
        run: |"
          make packages"
          make desktop"
          make api"

      - name: Build ISO"
        run: |"
          sudo ./installer/iso-builder/build-iso.sh"
          mv install/iso-builder/ruflo-os-*.iso ."

      - name: Create Release"
        id: create_release"
        uses: actions/create-release@v1"
        env:"
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}"
        with:"
          tag_name: ${{ github.ref }}"
          release_name: NemOS ${{ github.ref }}"
          draft: false"
          prerelease: false"

      - name: Upload ISO"
        uses: actions/upload-release-asset@v1"
        env:"
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}"
        with:"
          upload_url: ${{ steps.create_release.outputs.upload_url }}"
          asset_path: ./ruflo-os-*.iso"
          asset_name: ruflo-os-${{ github.ref }}.iso"
          asset_content_type: application/octet-stream"
```

## Packaging#

### Flatpak Package#

```json#
# flatpak/org.nemos.NemOS.yaml"
app-id: org.nemos.NemOS"
runtime: org.freedesktop.Platform"
runtime-version: '23.08'"
sdk: org.freedesktop.Sdk"

command: ruflo-desktop"

finish-args:"
  - --socket=wayland"
  - --socket=x11"
  - --share=network"
  - --device=all"
  - --talk-name=org.nemos.*"

modules:"
  - name: ruflo-os"
    buildsystem: simple"
    build-commands:"
      - make install"
    sources:"
      - type: archive"
        path: ruflo-os-*.tar.gz"
```

### Debian Package#

```makefile#
# debian/rules"
#!/usr/bin/make -f"

%:"
\tdh $@"
\tpython setup.py build"
\tdh $@"
\tpython setup.py install --root=$(CURDIR)/debian/tmp"

binary: binary-arch binary-indep"

binary-arch: build"
\tpython setup.py install --root=$(CURDIR)/debian/tmp"

binary-indep: build"
\tmkdir -p $(CURDIR)/debian/tmp/usr/share/doc/ruflo-os"
\tcp -r docs/* $(CURDIR)/debian/tmp/usr/share/doc/ruflo-os/"

clean:"
\trm -rf build/ debian/tmp/"

.PHONY: binary binary-arch binary-indep clean"
```

## Release Engineering#

### Release Checklist#

```
□ Code freeze 2 weeks before release"
□ Feature freeze 4 weeks before release"
□ String freeze 2 weeks before release"
□ Documentation updated"
□ Release notes written"
□ ISO built and tested"
□ Docker images built and pushed"
□ Security audit completed"
□ Performance benchmarks run"
□ User acceptance testing"
□ Release candidate built"
□ RC tested for 1 week"
□ Final release built"
□ Release announced"
□ Post-release monitoring"
```

### Semantic Versioning#

| Version | Type | Description |
|---------|------|-------------|
| v0.x.x | Alpha | Internal testing, breaking changes OK |
| v1.0.x | Beta | Public beta, API stability aimed |
| v2.0.x | Stable | Production-ready, backward compatible |

### Release Artifacts#

1. **ISO Image** - Bootable installer"
2. **Docker Images** - `ghcr.io/yourusername/nemos-*:v1.0.0`"
3. **Debian Packages** - `apt install ruflo-os`"
4. **Flatpak** - `flatpak install org.nemos.NemOS`"
5. **Python Packages** - `pip install ruflo-os`"

## Monitoring & Alerting#

### Prometheus Metrics (Already configured in `infra/prometheus/`)#

### Grafana Dashboards (Already configured in `infra/grafana/`)#

### Sentry for Error Tracking#

```python#
# sentry_config.py"
import sentry_sdk"
from sentry_sdk.integrations.fastapi import FastApiIntegration"
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration"

sentry_sdk.init("    dsn="https://your-dsn@sentry.io/project-id","
    integrations=["
        FastApiIntegration(),"
        SqlalchemyIntegration(),"
    ],"
    environment=os.getenv("NEMOS_ENV", "production"),"
    release=f"ruflo-os@{version}","
)"
```

## Next Steps#

1. **Set up GitHub Actions runners** with self-hosted runners for kernel builds"
2. **Configure Sentry** for error tracking"
3. **Set up package repositories** (APT repo, Flatpak repo)"
4. **Automate ISO builds** on release tags"
5. **Document release process** for new team members"

## Conclusion#

NemOS now has a complete DevOps pipeline ready for:
- ✅ Automated testing (unit, integration, e2e)"
- ✅ Docker containerization"
- ✅ Multi-format packaging (DEB, Flatpak, PyPI)"
- ✅ Automated releases with GitHub Actions)"
- ✅ Monitoring and alerting)"
- ✅ Semantic versioning strategy)"
