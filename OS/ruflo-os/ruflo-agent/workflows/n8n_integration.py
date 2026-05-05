"""
n8n Integration - n8n workflow triggers from Ruflo Agent.
Allows the agent to trigger n8n workflows for complex automation.
"""
import httpx
import structlog"
from typing import Dict, List, Any, Optional"

logger = structlog.get_logger(__name__)


class N8nIntegration:
    """
    Integration with n8n workflow automation platform.
    Triggers workflows from Ruflo Agent actions.
    """

    def __init__(self, n8n_url: str = "http://localhost:5678", api_key: Optional[str] = None):
        self.n8n_url = n8n_url.rstrip("/")
        self.headers = {}
        if api_key:
            self.headers["X-N8N-API-KEY"] = api_key

    def trigger_workflow(
        self, workflow_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Trigger an n8n workflow.
        Returns workflow execution result.
        """
        try:
            url = f"{self.n8n_url}/webhook/{workflow_id}"
            resp = httpx.post(url, json=data, headers=self.headers, timeout=30.0)
            resp.raise_for_status()
            logger.info("Workflow triggered", workflow_id=workflow_id)
            return {
                "success": True,
                "workflow_id": workflow_id,
                "response": resp.json() if resp.text else {}
            }
        except httpx.TimeoutException:
            logger.error("Workflow timeout", workflow_id=workflow_id)
            return {"success": False, "error": "Request timeout"}
        except Exception as e:
            logger.error("Workflow trigger failed", error=str(e))
            return {"success": False, "error": str(e)}

    def get_workflows(self) -> List[Dict]:
        """Get list of available workflows."""
        try:
            url = f"{self.n8n_url}/api/v1/workflows"
            resp = httpx.get(url, headers=self.headers, timeout=10.0)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            logger.error("Get workflows failed", error=str(e))
            return []

    def create_webhook_trigger(
        self, workflow_name: str, trigger_path: str
    ) -> Dict[str, Any]:
        """
        Create a webhook trigger for Ruflo Agent.
        Returns webhook URL for the agent to call.
        """
        try:
            url = f"{self.n8n_url}/api/v1/workflows"
            payload = {
                "name": workflow_name,
                "nodes": [
                    {
                        "type": "n8n-nodes-base.webhook",
                        "typeVersion": 1,
                        "position": [250, 300],
                        "name": "RufloAgentWebhook",
                        "parameters": {
                            "path": trigger_path,
                            "responseMode": "onReceived",
                            "responseData": "firstEntryJson"
                        }
                    }
                ]
            }
            resp = httpx.post(url, json=payload, headers=self.headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            webhook_url = f"{self.n8n_url}/webhook/{trigger_path}"
            logger.info("Webhook trigger created", workflow=workflow_name)
            return {
                "success": True,
                "workflow_id": data.get("id"),
                "webhook_url": webhook_url
            }
        except Exception as e:
            logger.error("Webhook creation failed", error=str(e))
            return {"success": False, "error": str(e)}


# Predefined workflow templates for Ruflo Agent
class RufloWorkflowTemplates:
    """Common workflow templates for Ruflo Agent."""

    @staticmethod
    def email_summary() -> Dict:
        """Workflow to summarize emails."""
        return {
            "name": "Ruflo Email Summary",
            "nodes": [
                {"type": "n8n-nodes-base.webhook", "name": "Webhook"},
                {"type": "n8n-nodes-base.gmail", "name": "Get Emails"},
                {"type": "n8n-nodes-base.ai", "name": "Summarize"},
                {"type": "n8n-nodes-base.emailSend", "name": "Send Summary"}
            ]
        }

    @staticmethod
    def research_pipeline() -> Dict:
        """Workflow for research tasks."""
        return {
            "name": "Ruflo Research Pipeline",
            "nodes": [
                {"type": "n8n-nodes-base.webhook", "name": "Webhook"},
                {"type": "n8n-nodes-base.httpRequest", "name": "Search Web"},
                {"type": "n8n-nodes-base.ai", "name": "Extract Key Info"},
                {"type": "n8n-nodes-base.googleSheets", "name": "Save Results"}
            ]
        }


if __name__ == "__main__":
    # Test n8n integration
    n8n = N8nIntegration()
    print("Testing n8n connection...")
    workflows = n8n.get_workflows()
    print(f"Found {len(workflows)} workflows")
