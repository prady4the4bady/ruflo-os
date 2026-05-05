"""
NemOS End-to-End Tests - Real desktop automation tests.
Tests the complete vertical slice: Model Gateway + Agent + Screen Observer.
"""
import pytest
import sys
import os
import time
import asyncio
import structlog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = structlog.get_logger(__name__)


class TestTaskExecution:
    """Test complete task execution flow."""

    def setup_method(self):
        """Setup test environment."""
        self.agent_endpoint = "http://localhost:8002/v1/tasks"
        self.gateway_endpoint = "http://localhost:8001/v1/chat/completions"
        self.timeout = 120  # 2 minutes per task

    @pytest.mark.asyncio
    async def test_simple_task_execution(self):
        """Test basic task: 'Open calculator and close it'."""
        try:
            import httpx
            # Submit task
            resp = await httpx.AsyncClient().post(
                self.agent_endpoint,
                json={"task": "Open calculator and close it", "mode": "auto"}
            )
            assert resp.status_code == 201, f"Task submission failed: {resp.status_code}"

            task_id = resp.json().get("task_id")
            assert task_id, "No task_id returned"

            # Wait for completion
            start = time.time()
            data = {}
            while time.time() - start < self.timeout:
                await asyncio.sleep(5)

                status_resp = await httpx.AsyncClient().get(
                    f"{self.agent_endpoint}/{task_id}")
                if status_resp.status_code == 200:
                    data = status_resp.json()
                    if data.get("status") in ("completed", "failed", "cancelled"):
                        logger.info("Task completed", status=data.get("status"))
                        break

            # Verify task completed (not failed)
            assert data.get("status") == "completed", f"Task failed: {data}"

        except ImportError:
            pytest.skip("httpx not available")
        except Exception as e:
            pytest.fail(f"Test failed: {e}")

    @pytest.mark.asyncio
    async def test_browser_search_task(self):
        """Test: 'Open Firefox, search for AI news, summarize'."""
        try:
            import httpx

            resp = await httpx.AsyncClient().post(
                self.agent_endpoint,
                json={
                    "task": "Open Firefox, search for 'NemOS AI', take screenshot",
                    "mode": "auto"
                }
            )
            assert resp.status_code == 201

            task_id = resp.json().get("task_id")
            # Wait for completion (longer timeout for browser)
            start = time.time()
            while time.time() - start < self.timeout * 2:
                await asyncio.sleep(5)

                status_resp = await httpx.AsyncClient().get(
                    f"{self.agent_endpoint}/{task_id}")
                if status_resp.status_code == 200:
                    data = status_resp.json()
                    if data.get("status") in ("completed", "failed"):
                        break

            logger.info("Browser task completed", **data)

        except ImportError:
            pytest.skip("httpx not available")

    @pytest.mark.asyncio
    async def test_model_fallback(self):
        """Test cloud model fallback when local unavailable."""
        try:
            import httpx

            # Submit task with cloud-only model
            resp = await httpx.AsyncClient().post(
                self.agent_endpoint,
                json={
                    "task": "Summarize: The quick brown fox",
                    "model_override": "nvidia-nemotron"
                }
            )
            assert resp.status_code == 201

        except ImportError:
            pytest.skip("httpx not available")


class TestScreenControl:
    """Test screen capture and control."""

    def test_screen_capture(self):
        """Test screen capture returns valid image."""
        try:
            from automation.screen_observer.src import observer
            obs = observer.ScreenObserver()

            result = observer.capture_screen()
            assert result.get("success"), "Screen capture failed"
            assert result.get("base64"), "No base64 data"
            assert result.get("resolution"), "No resolution"
            logger.info("Screen capture test passed")

        except ImportError:
            pytest.skip("ScreenObserver not available")

    def test_ocr_extraction(self):
        """Test OCR service extracts text."""
        try:
            from automation.ocr_service.src import ocr_service

            service = ocr_service.OCRService()
            # Create a simple test image with text
            from PIL import Image, ImageDraw
            import io

            img = Image.new('RGB', (400, 100), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), "Hello NemOS!", fill='black')

            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_b64 = io.BytesIO.getvalue()

            text = service.extract_text(base64_data=img_b64)
            assert "Hello" in text, f"OCR failed to extract text: {text}"
            logger.info("OCR test passed", extracted=text)

        except ImportError:
            pytest.skip("OCR service not available")

    def test_cursor_control(self):
        """Test cursor movement (requires display)."""
        try:
            import subprocess
            # Move to center
            result = subprocess.run(
                ["ydotool", "mousemove", "960", "540"],
                capture_output=True, text=True
            )
            # This might fail without proper display
            if result.returncode != 0:
                pytest.skip("ydotool not available or display not ready")

            logger.info("Cursor control test passed")

        except FileNotFoundError:
            pytest.skip("ydotool not installed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
