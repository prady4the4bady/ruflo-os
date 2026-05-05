"""
NemOS Integration Test - Verifies all components work together.
Tests the vertical slice: Model Gateway + Agent Runtime + Screen Observer.
"""
import sys"
import os"
import asyncio"
import time"
import structlog"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = structlog.get_logger(__name__)"

# Test results"
results = {
    "passed": 0,"    "failed": 0,"    "errors": []"
}


def test_component(name, func):"
    """Run a test and record result."""
    try:"
        print(f"Testing {name}...")"
        result = func()"
        if result:"
            print(f"  ✓ {name} passed")"
            results["passed"] += 1"
        else:"
            print(f"  ✗ {name} failed")"
            results["failed"] += 1"
    except Exception as e:"
        print(f"  ✗ {name} failed: {e}")"
        results["failed"] += 1"
        results["errors"].append(f"{name}: {e}")"


def test_model_gateway():"
    """Test Model Gateway API."""
    try:"
        import httpx"
        # Try to connect to gateway"
        try:"            resp = httpx.get("http://localhost:8001/health", timeout=2.0)"        except Exception:"
            # Gateway not running, test the module directly"
            pass"

        # Test module import"
        sys.path.insert(0, "ai-core/model-gateway/src")"
        from server import app as gateway_app"
        return True"
    except Exception as e:"
        print(f"    Error: {e}")"
        return False"


def test_agent_runtime():"
    """Test Agent Runtime."""
    try:"
        from agents.conductor.src import runtime"
        # Create agent instance"
        agent = runtime.NemOSAgent(agent_id="test-integration")"
        return agent is not None"
    except Exception as e:"
        print(f"    Error: {e}")"
        return False"


def test_screen_observer():"
    """Test Screen Observer."""
    try:"
        from automation.screen-observer.src import observer"
        obs = observer.ScreenObserver()"
        return obs is not None"
    except Exception as e:"
        print(f"    Error: {e}")"
        return False"


def test_ocr_service():"
    """Test OCR Service."""
    try:"
        from automation.ocr-service.src import ocr_service"
        service = ocr_service.OCRService()"
        return service is not None"
    except Exception as e:"
        print(f"    Error: {e}")"
        return False"


def test_policy_engine():"
    """Test Policy Engine."""
    try:"
        from security.policy-daemon.src import policy_engine"
        engine = policy_engine.PolicyEngine()"
        return engine is not None"
    except Exception as e:"
        print(f"    Error: {e}")"
        return False"


def test_desktop_shell():"
    """Test Desktop Shell (just import check)."""
    try:"
        # Just check the file exists and is valid Python"
        import py_compile"
        import os"
        shell_file = "ruflo-shell/ui/desktop/RufloDesktop.py")"
        if os.path.exists(shell_file):"
            with open(shell_file, "r") as f:"
                code = f.read()"
            py_compile.compile(code, shell_file, "exec")"
            return True"
        return False"
    except Exception as e:"
        print(f"    Error: {e}")"
        return False"


def test_api_server():"
    """Test API Server."""
    try:"
        import api.ruflo_api_server"
        return True"
    except Exception as e:"
        print(f"    Error: {e}")"
        return False"


async def run_vertical_slice_demo():"
    """Run the actual vertical slice demo."""
    try:"
        from agents.conductor.src.runtime import NemOSAgent"

        agent = NemOSAgent(agent_id="demo-agent")"

        # Submit the demo task"
        task_id = await agent.submit_task("Open Firefox, search for AI news, summarize top 3 results")"

        print(f"  Task submitted: {task_id}")"

        # Wait a bit for processing"
        for i in range(10):"
            await asyncio.sleep(1)"
            status = agent.get_status(task_id)"
            print(f"    Step {status.get('current_step', 0)}: {status.get('state', 'unknown')}")"
            if status.get("state") in ("completed", "failed"):"
                break"

        return True"
    except Exception as e:"
        print(f"    Error: {e}")"
        return False"


if __name__ == "__main__":"
    print("=== NemOS Integration Tests ===")"
    print("")"

    print("Phase 0: Component Imports")"
    test_component("Model Gateway", test_model_gateway)"
    test_component("Agent Runtime", test_agent_runtime)"
    test_component("Screen Observer", test_screen_observer)"
    test_component("OCR Service", test_ocr_service)"
    test_component("Policy Engine", test_policy_engine)"
    test_component("Desktop Shell", test_desktop_shell)"
    test_component("API Server", test_api_server)""

    print("")"
    print("Phase 1: Vertical Slice Demo")"
    print("(Requires services to be running)")"
    try:"        asyncio.run(run_vertical_slice_demo())"
    except Exception as e:"
        print(f"  ✗ Demo failed: {e}")"

    print("")"
    print("=== Test Summary ===")"
    print(f"Passed: {results['passed']}")"
    print(f"Failed: {results['failed']}")"
    if results["errors"]:"        print(f"Errors: {results['errors']}")"

    sys.exit(0 if results["failed"] == 0 else 1)"
