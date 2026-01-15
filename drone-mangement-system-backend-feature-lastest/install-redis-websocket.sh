#!/bin/bash

# Redis + WebSocket Installation Script
# Run this after the integration files have been added

echo "======================================"
echo "Redis + WebSocket Integration Setup"
echo "======================================"
echo ""

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found!"
    echo "Please run this script from the drone-mangement-system-backend directory"
    exit 1
fi

echo "✓ Found package.json"
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
echo "  - redis (Redis client)"
echo "  - socket.io (WebSocket server)"
echo ""

npm install redis socket.io

if [ $? -ne 0 ]; then
    echo "❌ npm install failed!"
    exit 1
fi

echo ""
echo "✓ Dependencies installed successfully"
echo ""

# Install type definitions (if TypeScript project)
if [ -f "tsconfig.json" ]; then
    echo "📦 Installing TypeScript definitions..."
    npm install --save-dev @types/node
    echo "✓ Type definitions installed"
    echo ""
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found"
    echo "Creating .env from template..."

    cat > .env << 'EOL'
# MongoDB Configuration
MONGODB_URI=mongodb+srv://your-connection-string

# Redis Configuration
REDIS_URL=redis://localhost:6379

# Server Configuration
PORT=5000
NODE_ENV=development
EOL

    echo "✓ Created .env file"
    echo "⚠️  Please update MONGODB_URI and REDIS_URL in .env"
    echo ""
else
    echo "✓ Found existing .env file"

    # Check if REDIS_URL is already in .env
    if ! grep -q "REDIS_URL" .env; then
        echo "Adding REDIS_URL to .env..."
        echo "" >> .env
        echo "# Redis Configuration" >> .env
        echo "REDIS_URL=redis://localhost:6379" >> .env
        echo "✓ Added REDIS_URL to .env"
    else
        echo "✓ REDIS_URL already exists in .env"
    fi
    echo ""
fi

# Test Redis connection
echo "🔍 Testing Redis connection..."
if command -v redis-cli &> /dev/null; then
    if redis-cli -h localhost -p 6379 ping > /dev/null 2>&1; then
        echo "✓ Redis is running and accessible"
    else
        echo "⚠️  Redis connection failed"
        echo "Please ensure Redis is running:"
        echo "  - Check Docker: docker ps | grep redis"
        echo "  - Or start Redis: redis-server"
    fi
else
    echo "⚠️  redis-cli not found (Redis might still work)"
fi

echo ""
echo "======================================"
echo "✓ Installation Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Update .env with your MONGODB_URI and REDIS_URL"
echo "2. Start the server: npm run dev"
echo "3. Open test-websocket-client.html in your browser"
echo "4. Test by creating/updating drones via API"
echo ""
echo "Documentation: See REDIS_WEBSOCKET_SETUP.md"
echo ""
