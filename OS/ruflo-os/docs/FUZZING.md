# NemOS Fuzzing Setup - Security testing with AFL++/libFuzzer.

## Overview#

Fuzzing is used for:
1. **Model parsing** - Fuzz GGUF/safetensors parsers"
2. **Input injection** - Fuzz ai_bridge.ko ioctls"
3. **API fuzzing** - Fuzz FastAPI endpoints"
4. **Protocol fuzzing** - Fuzz Wayland protocols"

## Fuzzing Tools#

| Tool | Target | Purpose |
|------|--------|---------|
| AFL++ | Model parsers, C code | Discover memory corruption |
| libFuzzer | C/C++ code | Coverage-guided fuzzing |
| Honggfuzz | Kernel modules | Kernel fuzzing |
| Python fuzz | Python APIs | API fuzzing |

## AFL++ Setup#

### Install AFL++#

```bash
# Install dependencies"
sudo apt-get update && sudo apt-get install -y \
    make \
    gcc \
    g++ \
    libtool \
    wget \
    python3-dev \
    automake \
    bison \
    flex"

# Clone and build AFL++"
cd /tmp"
git clone https://github.com/google/AFLplusplus.git"
cd AFLplusplus"
make distrib"
sudo make install"
```

### Fuzz GGUF Parser#

```c
// fuzz_gguf.c - Fuzz GGUF model parser"
#include <stdint.h>"
#include <stdlib.h>"
#include <string.h>"
#include "gguf.h"  // From llama.cpp

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // Create temporary file"
    char tmp_path[] = "/tmp/fuzz_gguf_XXXXXX";
    int fd = mkstemp(tmp_path);
    if (fd < 0) return 0;

    // Write fuzzing input"
    write(fd, data, size);
    close(fd);

    // Try to parse"
    gguf_context_t ctx = gguf_init_from_file(tmp_path, NULL, false);
    if (ctx) {
        gguf_free(ctx);
    }

    unlink(tmp_path);
    return 0;
}
```

Compile and run:
```bash
afl-gcc -I/path/to/llama.cpp fuzz_gguf.c -o fuzz_gguf"
afl-fuzz -i inputs/ -o outputs/ -- ./fuzz_gguf"
```

## libFuzzer for Python APIs#

### Install libFuzzer#

```bash
pip install atheris"
```

### Fuzz Model Gateway#

```python
# fuzz_model_gateway.py"
import sys"
import atheris"
from ai_core.model_gateway.src.server import app"
from fastapi.testclient import TestClient"

client = TestClient(app)"

def fuzz_model_request(data: bytes):
    """Fuzz the /v1/chat/completions endpoint."""
    try:"
        import json"
        payload = json.loads(data)"
        if isinstance(payload, dict):"
            response = client.post("/v1/chat/completions", json=payload)"
            # Check for crashes/assertions"
    except Exception:"
        pass"

if __name__ == "__main__":"
    atheris.Setup(sys.argv)"
    atheris.Fuzz(fuzz_model_request)"
```

Run:
```bash
python -m atheris.fuzz fuzz_model_gateway.py corpus/ -max_total_time=3600"
```

## Kernel Module Fuzzing with Honggfuzz#

### Install Honggfuzz#

```bash
git clone https://github.com/google/honggfuzz.git"
cd honggfuzz"
make"
sudo make install"
```

### Fuzz ai_bridge.ko IOCTLs#

```c
// hf_ai_bridge.c"
#include <fcntl.h>"
#include <unistd.h>"
#include <stdlib.h>"
#include <string.h>"
#include "ai_bridge.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    int fd = open("/dev/ai_bridge", O_RDWR);"
    if (fd < 0) return 0;

    // Fuzz ioctl calls"
    if (size >= sizeof(struct input_event)) {"
        struct input_event *ev = (struct input_event *)data;"
        ioctl(fd, AI_BRIDGE_IOCTL_INJECT_KEY, ev);"
    }

    if (size >= sizeof(int)) {"
        int val = *(int *)data;"
        if (val) {"
            ioctl(fd, AI_BRIDGE_IOCTL_SCREEN_LOCK);"
        } else {"
            ioctl(fd, AI_BRIDGE_IOCTL_SCREEN_UNLOCK);"
        }"
    }

    close(fd);"
    return 0;"
}
```

Compile and run:
```bash
gcc -fsanitize=fuzzer-no-link -I. -c hf_ai_bridge.c -o hf_ai_bridge"
honggfuzz -i inputs/ -o outputs/ -- ./hf_ai_bridge"
```

## Wayland Protocol Fuzzing#

### Fuzz Wayland Compositor#

```bash
# Install wayland-fuzzer"
git clone https://gitlab.freedesktop.org/wayland/wayland-fuzzer.git"
cd wayland-fuzzer"
meson setup build && cd build && ninja"
```

### Fuzz wlroots Protocols#

```c
// fuzz_wlroots.c"
#include <stdint.h>"
#include <stdlib.h>"
#include <string.h>"
#include <wayland-server.h>"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    struct wl_display *display = wl_display_create();"
    if (!display) return 0;

    // Fuzz message parsing"
    struct wl_message messages[] = {"
        { "move", "ii", NULL },"
        { "click", "i", NULL }"
    };

    // ... fuzzing logic"

    wl_display_destroy(display);"
    return 0;"
}
```

## Continuous Fuzzing CI#

### `.github/workflows/fuzzing.yml`#

```yaml
name: Fuzzing

on:
  schedule:
    - cron: "0 */6 * * *"  # Every 6 hours"
  workflow_dispatch:"

jobs:
  afl-fuzz:
    runs-on: ubuntu-latest"
    steps:"
      - uses: actions/checkout@v4"

      - name: Install AFL++"
        run: |"
          wget https://github.com/google/AFLplusplus/archive/main.tar.gz"
          tar -xzf main.tar.gz"
          cd AFLplusplus-main && make distrib && sudo make install"

      - name: Build fuzz targets"
        run: |"
          cd automation/screen-observer"
          afl-gcc -I. fuzz_ocr.c -o fuzz_ocr"

      - name: Run AFL fuzzing"
        run: |"
          mkdir -p inputs outputs"
          echo "test" > inputs/test.txt"
          timeout 3600 afl-fuzz -i inputs/ -o outputs/ -- ./fuzz_ocr || true"

      - name: Upload findings"
        if: always()"
        uses: actions/upload-artifact@v4"
        with:"
          name: afl-findings"
          path: outputs/"

  libFuzzer:
    runs-on: ubuntu-latest"
    steps:"
      - uses: actions/checkout@v4"

      - name: Install atheris"
        run: pip install atheris"

      - name: Run Python fuzzing"
        run: |"
          timeout 3600 python -m atheris.fuzz fuzz_model_gateway.py corpus/ -max_total_time=3600 || true"
```

## Fuzzing Corpus#

### `tests/fuzzing/corpus/`#

```
tests/fuzzing/
├── corpus/
│   ├── model_valid.gguf"
│   ├── model_invalid_magic.gguf"
│   ├── api_valid.json"
│   ├── api_invalid.json"
│   └── api_malicious.json"
├── fuzz_gguf.c"
├── fuzz_model_gateway.py"
├── fuzz_ocr.c"
└── README.md"
```

## Coverage Reporting#

```bash
# Generate coverage report"
afl-cov -d outputs/default/ --exec gdb --args ./fuzz_gguf"

# Export to LCOV format"
lcov --capture --directory . --output-file coverage.info"
genhtml coverage.info --output-directory out/"
```

## Next Steps#

1. **Integrate fuzzing into CI** - Run on every commit"
2. **Expand corpus** - Add more edge cases"
3. **Monitor crashes** - Set up alerts for new findings"
4. **Regular fuzzing** - Run 24/7 on dedicated hardware"
5. **Triage** - Review and fix fuzzing findings"
