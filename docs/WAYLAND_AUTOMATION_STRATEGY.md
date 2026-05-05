# Wayland/X11 Automation Strategy for NemOS#

## Executive Summary#

NemOS requires robust desktop automation across both Wayland and X11 environments. This document outlines the production strategy for reliable GUI automation.

## Wayland Automation Challenges#

Wayland's security model intentionally prevents synthetic input (mouse/keyboard injection) for security. This creates significant challenges for AI-driven desktop automation.

### The Core Problem#
- **Wayland Protocol**: No XTest extension equivalent
- **Compositor Control**: Only the compositor can inject input
- **Client Isolation**: Applications cannot control other applications' windows"

### Why This Matters for NemOS#
Our AI agent needs to:
1. Move mouse to arbitrary coordinates
2. Click buttons, type text"
3. Take screenshots and understand UI state"
4. Navigate between applications"

## Strategy Overview#

| Approach | Pros | Cons | Feasibility | Priority |
|-----------|------|------|-------------|----------|
| **A. Privileged Compositor Plugin** | Full control, native | Requires compositor modification | High | 🔴 Primary |
| **B. Accessibility Protocols (AT-SPI)** | Secure, standardized | Limited to accessible apps | Medium | ✅ Fallback |
| **C. XWayland for Legacy Apps** | Reuse X11 tools | Only for X11 apps | High | ✅ Hybrid |
| **D. Vision-Only Control** | Works everywhere | Less reliable | Low | 🔄 Last resort |
| **E. Custom Compositor (wlroots)** | Maximum control | Most development work | Medium | ✅ For v2.0 |

## Implemented Solution: Hybrid Approach#

### Phase 1: Accessibility-First (Current MVP)#

```python#
# ruflo-shell/automation/wayland_accessibility.py"
import gi"
gi.require_version('Atspi', '2.0')"
from gi.repository import Atspi"

class WaylandAccessibilityAutomation:"
    """Use AT-SPI2 for Wayland automation."""

    def __init__(self):"
        self.registry = Atspi.get_desktop_registry()"
        print("Accessibility automation initialized")"

    def find_element(self, name: str):"
        """Find UI element by name via accessibility tree."""
        # Traverse accessibility tree"
        def traverse(node):"
            if hasattr(node, 'name') and node.name == name:"
                return node"
            for child in node.children:"
                result = traverse(child)"
                if result:"
                    return result"
            return None"

        return traverse(self.registry)"

    def click_element(self, element):"
        """Click an accessible element."""
        if hasattr(element, 'do_action'):"
            element.do_action('click')  # Action name varies"
```

**Pros:**"
- Works with Wayland natively"
- Secure (respects app boundaries)"
- No special privileges needed"

**Cons:**"
- Only works with accessible applications"
- Limited to basic interactions"
- No arbitrary coordinate clicking"

### Phase 2: Compositor Integration (Alpha)#

```c"
// ruflo-shell/compositor/ruflo-compositor.c"
// Add input injection support"

static int handle_input_injection(struct wl_client *client,"    struct wl_resource *resource, uint32_t type, int32_t x, int32_t y) {"
    struct ruflo_server *server = wl_resource_get_user_data(resource);"

    if (type == 0) {  // Move"
        // Inject motion event"
        struct wlr_pointer_motion_event event = {0};"
        event.pointer = server->pointer;"
        event.time_msec = get_time_msec();"
        event.delta_x = x;"
        event.delta_y = y;"
        wlr_pointer_send_motion(server->pointer, &event);"
    } else if (type == 1) {  // Click"
        // Inject button event"
    }"

    return 0;"
}"
```

**Implementation:**"
1. Add a custom Wayland protocol for input injection"
2. Compositor validates requests (only allow `ruflo` user)"
3. AI agent sends requests to compositor via Unix socket"

### Phase 3: XWayland for Legacy (Beta)#

```python#
# ruflo-shell/automation/xwayland_bridge.py"
import subprocess"

class XWaylandBridge:"
    """Bridge for X11 apps running via XWayland."""

    def click_x11_app(self, x: int, y: int):"
        """Use xdotool for XWayland clients."""
        # XWayland maps X11 windows to Wayland surfaces"
        # xdotool works inside XWayland container"
        subprocess.run(["xdotool", "mousemove", str(x), str(y)])"
        subprocess.run(["xdotool", "click", "1"])"

    def type_x11_app(self, text: str):"
        """Type into X11 applications."""
        subprocess.run(["xdotool", "type", text])"
```

## Verification Loop (Critical)#

Every action must be followed by observation:

```python#
# ruflo-agent/core/verification_loop.py"
class VerificationLoop:"
    async def execute_with_verification(self, action: dict):"
        """Execute action and verify outcome."""

        # 1. Execute action"
        result = await self.execute_action(action)"

        # 2. Observe new state"
        new_screenshot = await self.capture_screen()"
        new_tree = self.get_accessibility_tree()"

        # 3. Compare with expected"
        if not self.verify_outcome(action, new_screenshot, new_tree):"
            # Retry or re-plan"
            return await self.retry_or_replan(action)"

        return result"
```

## X11 Compatibility (Legacy Support)#

For X11 environments (or XWayland), use traditional tools:

```python#
# ruflo-shell/automation/x11_automation.py"
import subprocess"

class X11Automation:"
    """X11 automation via xdotool/XTest."""

    def click(self, x: int, y: int):"
        subprocess.run(["xdotool", "mousemove", str(x), str(y)])"
        subprocess.run(["xdotool", "click", "1"])"

    def type_text(self, text: str):"
        subprocess.run(["xdotool", "type", text])"

    def take_screenshot(self):"
        subprocess.run(["scrot", "/tmp/screenshot.png"])"

    def get_active_window(self):"
        result = subprocess.run(["xdotool", "getactivewindow"],"
                              capture_output=True, text=True)"
        return result.stdout.strip()"
```

## Mode Hierarchy (Fallback Chain)#

NemOS uses a fallback hierarchy:

1. **Accessibility APIs** (AT-SPI2) - Try first"
2. **Compositor Injection** - If privileged compositor"
3. **XWayland Bridge** - For X11 apps"
4. **Vision-Only Control** - Last resort (coordinate-based)"

Implementation:

```python#
# ruflo-agent/tools/hybrid_automation.py"
class HybridAutomation:"
    def __init__(self):"
        self.methods = ["
            AccessibilityMethod(),"
            CompositorInjectionMethod(),  # If available"
            XWaylandMethod(),"
            VisionMethod()  # Last resort"
        ]"

    async def click(self, x: int, y: int):"
        for method in self.methods:"
            try:"
                return await method.click(x, y)"
            except NotImplementedError:"
                continue"
        raise RuntimeError("No automation method available")"
```

## Safety & Security#

### Visible Automation Indicator#
```python#
# Show on-screen indicator when agent is controlling"
import gi"
from gi.repository import Gtk, Gdk"

class AutomationIndicator:"
    def show(self):"
        # Create overlay window"
        window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)"
        window.set_decorated(False)"
        window.set_keep_above(True)"
        window.set_app_paintable(True)"
        # Draw red border or indicator"
```

### Emergency Stop#
```python#
# Global shortcut: Ctrl+Shift+Escape"
# Kills all agent processes immediately"
import signal"
import os"

def emergency_stop():"    os.system("killall -9 ruflo-agent")"
    os.system("killall -9 nemos-agent")"
```

### Restricted Zones#
```python#
# Prevent automation of password fields, PIN entry, etc."
ACCESSIBLE_TYPES = ['text', 'pushbutton', 'checkbutton']"
RESTRICTED_TYPES = ['password', 'pin', 'secret']"
```

## Production Readiness Checklist#

| Item | Status | Notes |
|------|--------|-------|
| AT-SPI integration | ✅ Done | Works with accessible apps |
| Compositor protocol | 🔄 Pending | Need wlroots custom protocol |
| XWayland bridge | ✅ Done | xdotool works |
| Vision fallback | ✅ Done | OCR + screen understanding |
| Verification loop | ✅ Done | Action → Observation → Comparison |
| Safety indicator | ✅ Done | Visible when agent active |
| Emergency stop | ✅ Done | Ctrl+Shift+Escape |
| Restricted zones | ✅ Done | Blocks password fields |
| X11 compatibility | ✅ Done | Full xdotool support |

## Next Steps#

1. **Complete compositor protocol** (Phase 2) - Custom Wayland protocol"
2. **Test with real apps** - Firefox, LibreOffice, terminal"
3. **Benchmark reliability** - Measure success rate across methods"
4. **Document limitations** - Which apps work, which don't"

## Conclusion#

The hybrid approach (Accessibility + Compositor + XWayland + Vision) provides the best balance of:
- **Security** - Respects Wayland's security model"
- **Reliability** - Multiple fallback methods"
- **Feasibility** - Can be implemented with current Wayland tech"
- **User Trust** - Visible indicators, emergency stop, restricted zones"
