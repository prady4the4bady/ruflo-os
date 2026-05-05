import asyncio
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_tool import BaseTool
import structlog

logger = structlog.get_logger(__name__)

class BrowserTool(BaseTool):
    """Browser automation using Playwright with fallback to cursor control."""

    name = "browser_tool"
    description = "Open URLs, interact with web pages"

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None

    async def initialize(self) -> None:
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=False)
            self.page = await self.browser.new_page()
            logger.info("Browser initialized")

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        await self.initialize()
        try:
            if action == "open_url":
                return await self.open_url(kwargs["url"])
            elif action == "click_element":
                return await self.click_element(kwargs["selector"])
            elif action == "type_in_field":
                return await self.type_in_field(kwargs["selector"], kwargs["text"])
            elif action == "get_page_text":
                return await self.get_page_text()
            elif action == "take_screenshot":
                return await self.take_screenshot()
            elif action == "execute_js":
                return await self.execute_js(kwargs["code"])
            else:
                return {"success": False, "error": f"Unknown action {action}"}
        except Exception as e:
            logger.error("Browser action failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def open_url(self, url: str) -> Dict[str, Any]:
        await self.page.goto(url)
        logger.info("URL opened", url=url)
        return {"success": True, "url": url, "title": await self.page.title()}

    async def click_element(self, selector: str) -> Dict[str, Any]:
        await self.page.click(selector)
        return {"success": True}

    async def type_in_field(self, selector: str, text: str) -> Dict[str, Any]:
        await self.page.fill(selector, text)
        return {"success": True}

    async def get_page_text(self) -> str:
        return await self.page.inner_text("body")

    async def take_screenshot(self) -> Dict[str, Any]:
        screenshot = await self.page.screenshot()
        return {"success": True, "screenshot": screenshot}

    async def execute_js(self, code: str) -> Any:
        return await self.page.evaluate(code)