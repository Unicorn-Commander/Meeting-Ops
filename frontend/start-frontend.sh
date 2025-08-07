#!/bin/bash
# Meeting-Ops Frontend Startup Script

echo "🎨 Starting Meeting-Ops Frontend..."

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Check if backend is running
echo "🔍 Checking if backend is running on port 9050..."
if ! nc -z localhost 9050 2>/dev/null; then
    echo "⚠️ Backend not detected on port 9050"
    echo "💡 Start backend with: cd ../backend && ./start-backend.sh"
    echo ""
fi

echo "🚀 Starting frontend development server on port 7777..."
echo "🌐 Access at: http://localhost:7777"
echo "👥 Login credentials:"
echo "   Admin: admin / admin123"
echo "   User:  user / user123"
echo ""

npm run dev