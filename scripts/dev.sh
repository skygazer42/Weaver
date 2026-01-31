#!/bin/bash

# Development startup script

set -e

echo "🚀 Starting Weaver App in development mode..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please run ./scripts/setup.sh first"
    exit 1
fi

# Start database if not running
if ! docker ps | grep -q manus_postgres; then
    echo "🗄️  Starting PostgreSQL database..."
    docker-compose up -d postgres
    echo "⏳ Waiting for database to be ready..."
    sleep 3
fi

# Start backend
echo "🐍 Starting backend server..."
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start web
echo "⚛️  Starting web server..."
cd web
npm run dev &
WEB_PID=$!
cd ..

echo ""
echo "✅ Development servers started!"
echo ""
echo "📍 URLs:"
echo "   Web:      http://localhost:3000"
echo "   Backend:  http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all servers"

# Cleanup on exit
trap "kill $BACKEND_PID $WEB_PID 2>/dev/null; exit" SIGINT SIGTERM

# Wait for processes
wait
