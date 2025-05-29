#!/bin/bash

echo "🚀 Starting Support Flow..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Start processing service in background
echo -e "${YELLOW}📡 Starting processing service on port 8080...${NC}"
cd 03-processing
if [ -d "venv" ]; then
    source venv/bin/activate
    uvicorn main:app --reload --port 8080 &
    PROCESSING_PID=$!
    echo -e "${GREEN}✅ Processing service started (PID: $PROCESSING_PID)${NC}"
    deactivate
else
    echo "❌ Processing service venv not found. Run ./setup.sh first"
    exit 1
fi
cd ..

# Start backend in background
echo -e "${YELLOW}🔧 Starting backend on port 8000...${NC}"
cd 02-backend
if [ -d "venv" ]; then
    source venv/bin/activate
    uvicorn main:app --reload --port 8000 &
    BACKEND_PID=$!
    echo -e "${GREEN}✅ Backend started (PID: $BACKEND_PID)${NC}"
    deactivate
else
    echo "❌ Backend venv not found. Run ./setup.sh first"
    exit 1
fi

# Start frontend
echo -e "${YELLOW}🌐 Starting frontend on port 3000...${NC}"
cd ../01-frontend
if [ -d "node_modules" ]; then
    echo -e "${GREEN}✅ Starting frontend (this will block, use Ctrl+C to stop all services)${NC}"
    npm run dev
else
    echo "❌ Frontend node_modules not found. Run ./setup.sh first"
    exit 1
fi 