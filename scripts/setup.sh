#!/bin/bash

# Manus App Setup Script

set -e

echo "🚀 Setting up Manus App..."

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11+ first."
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

echo "✅ Prerequisites check passed"

# Setup environment files
echo "📝 Setting up environment files..."

if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Created .env file. Please fill in your API keys!"
fi

if [ ! -f frontend/.env.local ]; then
    cp frontend/.env.local.example frontend/.env.local
fi

if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
fi

echo "✅ Environment files created"

# Install root dependencies
echo "📦 Installing root dependencies..."
npm install

# Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd frontend
npm install
cd ..

# Setup Python virtual environment
echo "🐍 Setting up Python virtual environment..."
cd backend
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

deactivate
cd ..

# Start database
echo "🗄️  Starting PostgreSQL database..."
docker-compose up -d postgres

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
echo "   npm run dev"
echo ""
echo "3. Open http://localhost:3000 in your browser"
echo ""
echo "🎉 Happy coding!"
