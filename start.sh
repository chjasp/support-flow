#!/bin/bash

echo "🚀 Starting Support Flow..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Start processing service in background (if it exists)
if [ -d "03-processing" ]; then
    echo -e "${YELLOW}📡 Starting processing service on port 8080...${NC}"
    cd 03-processing
    if [ -d "venv" ] && [ -f "main.py" ]; then
        source venv/bin/activate
        uvicorn main:app --reload --port 8080 &
        PROCESSING_PID=$!
        echo -e "${GREEN}✅ Processing service started (PID: $PROCESSING_PID)${NC}"
        deactivate
    else
        echo -e "${RED}❌ Processing service venv or main.py not found. Skipping processing service.${NC}"
    fi
    cd ..
else
    echo -e "${YELLOW}⚠️  Processing service directory not found. Skipping processing service.${NC}"
fi

# Start simplified backend in background
echo -e "${YELLOW}🔧 Starting simplified backend on port 8000...${NC}"
cd 02-backend
if [ -d "venv" ] && [ -f "main.py" ]; then
    source venv/bin/activate
    uvicorn main:app --reload --port 8000 &
    BACKEND_PID=$!
    echo -e "${GREEN}✅ Simplified backend started (PID: $BACKEND_PID)${NC}"
    deactivate
else
    echo -e "${RED}❌ Backend venv or main.py not found. Run ./setup.sh first${NC}"
    exit 1
fi

# Start frontend
echo -e "${YELLOW}🌐 Starting frontend on port 3000...${NC}"
cd ../01-frontend
if [ -d "node_modules" ]; then
    echo -e "${GREEN}✅ Starting frontend (this will block, use Ctrl+C to stop all services)${NC}"
    npm run dev
else
    echo -e "${RED}❌ Frontend node_modules not found. Run ./setup.sh first${NC}"
    exit 1
fi 