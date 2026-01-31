#!/usr/bin/env bash

# Development startup script

set -euo pipefail

echo "🚀 Starting Weaver App in development mode..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please run ./scripts/setup.sh first"
    exit 1
fi

compose() {
    if docker compose version &>/dev/null; then
        docker compose -f docker/docker-compose.yml "$@"
        return
    fi
    if command -v docker-compose &>/dev/null; then
        docker-compose -f docker/docker-compose.yml "$@"
        return
    fi
    echo "❌ Docker Compose not found. Install Docker Desktop or docker-compose."
    exit 1
}

# Start database (idempotent)
echo "🗄️  Ensuring PostgreSQL database is running..."
compose up -d postgres
echo "⏳ Waiting for database to be ready..."
sleep 3

# Start backend
echo "🐍 Starting backend server..."
if [ ! -d .venv ]; then
    echo "❌ .venv not found. Please run ./scripts/setup.sh (or make setup) first."
    exit 1
fi
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start web
echo "⚛️  Starting web server..."
pnpm -C web dev &
WEB_PID=$!

echo ""
echo "✅ Development servers started!"
echo ""
echo "📍 URLs:"
echo "   Web:      http://localhost:3100"
echo "   Backend:  http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all servers"

# Cleanup on exit
trap "kill $BACKEND_PID $WEB_PID 2>/dev/null; exit" SIGINT SIGTERM

# Wait for processes
wait
