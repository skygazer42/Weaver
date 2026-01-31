#!/usr/bin/env bash

# Weaver App Setup Script

set -euo pipefail

echo "🚀 Setting up Weaver App..."

# Check prerequisites
echo "📋 Checking prerequisites..."

need_cmd() {
    if ! command -v "$1" &>/dev/null; then
        echo "❌ Missing dependency: $1"
        exit 1
    fi
}

# Node tooling
need_cmd node
need_cmd pnpm

# Backend tooling
need_cmd make
if command -v python3.11 &>/dev/null; then
    PYTHON="python3.11"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
    echo "⚠️  python3.11 not found; falling back to python3. Makefile defaults to python3.11."
else
    echo "❌ Python 3 is not installed. Please install Python 3.11+ first."
    exit 1
fi

# Docker / Compose
need_cmd docker

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

echo "✅ Prerequisites check passed"

# Setup environment files
echo "📝 Setting up environment files..."

if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Created .env file. Please fill in your API keys!"
fi

if [ ! -f web/.env.local ]; then
    cp web/.env.local.example web/.env.local
fi

echo "✅ Environment files created"

# Setup backend (.venv + deps)
echo "🐍 Installing backend dependencies..."
make PYTHON="$PYTHON" setup

# Setup frontend deps
echo "⚛️  Installing web dependencies..."
pnpm -C web install --frozen-lockfile

# Start database
echo "🗄️  Starting PostgreSQL database..."
compose up -d postgres

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 5

echo "✅ Setup complete!"
echo ""
echo "📚 Next steps:"
echo "1. Edit .env and add your API keys:"
echo "   - OPENAI_API_KEY (required)"
echo "   - TAVILY_API_KEY (required for search)"
echo "   - E2B_API_KEY (optional, for code execution)"
echo ""
echo "2. Start the development servers:"
echo "   ./scripts/dev.sh"
echo ""
echo "3. Open http://localhost:3100 in your browser"
echo ""
echo "🎉 Happy coding!"
