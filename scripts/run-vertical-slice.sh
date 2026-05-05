#!/bin/bash"
# NemOS Vertical Slice Demo - 30-Day Build Plan"
# Demonstrates: "Open Firefox, search for AI news, summarize top 3 articles""

set -e"
echo "=== NemOS Vertical Slice Demo ===""

# Phase 1: Bootstrap (Days 1-3)"
echo "Phase 1: Bootstrapping...""
./scripts/bootstrap.sh"

# Phase 2: Desktop Shell (Days 4-7)""
echo "Phase 2: Building desktop shell...""
cd platform/desktop-shell"
if [ ! -f "build/compile_commands.json" ]; then"
    meson setup build"
fi"
cd build && ninja"
cd ../.."

# Phase 3: Model Gateway (Days 8-12)""
echo "Phase 3: Starting Model Gateway...""
cd ai-core/model-gateway"
if [ ! -f ".env" ]; then"
    echo "OPENAI_API_KEY=your-key-here" > .env"
    echo "NEMOS_ALLOW_CLOUD=true" >> .env"
fi"
uvicorn src.server:app --port 8001 --daemon"
cd ../.."

# Phase 4: Single-Agent Runtime (Days 13-18)""
echo "Phase 4: Starting Agent Runtime...""
cd agents/conductor/src"
uvicorn runtime:app --port 8002 --daemon"
cd ../../../"

# Phase 5: Screen Capture + OCR (Days 19-23)""
echo "Phase 5: Testing screen capture...""
cd automation/screen-observer/src"
python -c "from observer import ScreenObserver; import asyncio; obs = ScreenObserver(); result = asyncio.run(obs.capture_screen()); print('Screenshot captured:', result['success'])""
cd ../../../"

# Phase 6: Policy Engine (Days 24-27)""
echo "Phase 6: Testing policy engine...""
cd security/policy-daemon/src"
python -c "from policy_engine import PolicyEngine; pe = PolicyEngine(); print('Policy engine loaded'); print('Policies:', len(pe.policies))"\
cd ../../../"

# Run the Demo"
echo """"
echo "=== Running Vertical Slice Demo ===""

DEMO_TASK="Open Firefox, search for 'AI news', summarize top 3 articles, save to ~/Documents/ai_news_summary.txt""

echo "Submitting task: $DEMO_TASK""

# Submit task to agent"
curl -X POST http://localhost:8002/v1/tasks \
  -H "Content-Type: application/json" \
  -d "{\"task\": \"$DEMO_TASK\", \"mode\": \"auto\"}""

echo """"
echo "=== Demo task submitted! ==="\
echo "Check status at: http://localhost:8002/v1/tasks/{task_id}"\
echo "Agent UI at: http://localhost:3000 (if desktop shell running)""
echo """"

# Wait for completion (simplified)"
echo "Waiting for task completion..."\
for i in {1..60}; do"
    sleep 5"
    echo -n "."\
done"
echo """

echo "=== Vertical Slice Demo Complete ==="\
echo "Check results in ~/Documents/ai_news_summary.txt"\
