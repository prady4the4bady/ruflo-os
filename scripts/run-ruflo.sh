#!/bin/bash
set -e
echo "=== Starting Ruflo OS Stack ==="

# Start Nemoclaw daemon
echo "Starting Nemoclaw Daemon..."
python3 -m nemoclaw.core.nemoclaw_daemon &
sleep 2

# Start Ruflo Agent
echo "Starting Ruflo Agent..."
python3 -m ruflo-agent.core.agent_runtime &
sleep 2

# Start Hermes Integration
echo "Starting Hermes Client..."
python3 -m hermes-integration.hermes_client &
sleep 1

# Start Ruflo API Server
echo "Starting Ruflo API Server..."
uvicorn api.ruflo_api_server:app --host 0.0.0.0 --port 7474 &
sleep 1

# Start Ruflo Shell (requires display)
echo "Starting Ruflo Shell..."
ruflo-compositor &
echo "=== Ruflo OS Stack Started ==="
echo "API available at http://localhost:7474"
echo "Submit tasks via POST /api/v1/tasks"

# Wait for all processes
wait