import structlog
from typing import Optional

logger = structlog.get_logger(__name__)

class ModelSwitcher:
    """Handle /model command for runtime model switching."""

    def __init__(self, nemoclaw_router=None):
        self.router = nemoclaw_router

    async def switch_model(self, model_id: str, preserve_state: bool = True) -> dict:
        """Switch model mid-task, preserving state."""
        if not self.router:
            return {"success": False, "error": "Router not initialized"}

        old_model = self.router.default_model_id
        try:
            self.router.hot_swap(model_id)
            logger.info("Model switched", old=old_model, new=model_id, preserve_state=preserve_state)
            return {
                "success": True,
                "old_model": old_model,
                "new_model": model_id,
                "state_preserved": preserve_state
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_available_models(self) -> list:
        if not self.router:
            return []
        return [
            {"id": m.id, "name": m.name, "loaded": m.loaded}
            for m in self.router.list_models()
        ]