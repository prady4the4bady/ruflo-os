# Ruflo OS API Reference

## REST Endpoints

### POST /api/v1/tasks
Submit a new task to the Ruflo Agent.
- **Request**: `{ "task": "string", "mode": "auto|manual", "model_override": "string?" }`
- **Response**: `{ "task_id": "uuid", "status": "queued", "estimated_steps": int }`

### GET /api/v1/tasks/{task_id}
Get task status and progress.
- **Response**: `{ "task_id", "status", "progress", "current_action", "result" }`

### DELETE /api/v1/tasks/{task_id}
Cancel a running task.

### GET /api/v1/tasks/history
List completed/cancelled tasks.

### GET /api/v1/screen/screenshot
Get current screen as base64 PNG.

### GET /api/v1/models
List available models from registry.

### POST /api/v1/models/pull
Pull a new model from HuggingFace or GitHub.
- **Request**: `{ "source": "huggingface|github|ollama", "identifier": "string" }`

### DELETE /api/v1/models/{model_id}
Remove a model from registry.

### GET /api/v1/agent/status
Get current agent state, active task, memory usage.

### POST /api/v1/agent/pause
Pause the running agent.

### POST /api/v1/agent/resume
Resume a paused agent.

### POST /api/v1/agent/reset
Reset agent state.

## WebSocket Endpoints

### WS /ws/tasks/{task_id}/stream
Real-time JSON stream of agent actions:
`{ "type": "thought|action|observation|complete", "data": {...}, "timestamp": float }`

### WS /ws/screen/stream
Real-time screen frames at configurable FPS (1-30fps), base64 PNG.

### WS /ws/agent/events
All agent events across all tasks.