#!/bin/bash

echo "🛑 Stopping Support Flow services..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to kill processes on specific ports
kill_port() {
    local port=$1
    local service_name=$2
    
    echo -e "${YELLOW}🔍 Looking for $service_name on port $port...${NC}"
    
    # Find process using the port
    PID=$(lsof -ti:$port)
    
    if [ ! -z "$PID" ]; then
        echo -e "${YELLOW}📱 Found $service_name (PID: $PID), stopping...${NC}"
        kill -TERM $PID 2>/dev/null
        
        # Wait a moment for graceful shutdown
        sleep 2
        
        # Check if still running, force kill if necessary
        if kill -0 $PID 2>/dev/null; then
            echo -e "${YELLOW}⚡ Force killing $service_name...${NC}"
            kill -KILL $PID 2>/dev/null
        fi
        
        echo -e "${GREEN}✅ $service_name stopped${NC}"
    else
        echo -e "${GREEN}✅ $service_name not running${NC}"
    fi
}

# Stop all services
kill_port 3000 "Frontend (Next.js)"
kill_port 8000 "Backend (FastAPI)"
kill_port 8080 "Processing Service (FastAPI)"

# Also kill any remaining uvicorn processes
echo -e "${YELLOW}🧹 Cleaning up any remaining uvicorn processes...${NC}"
pkill -f "uvicorn.*main:app" 2>/dev/null && echo -e "${GREEN}✅ Cleaned up uvicorn processes${NC}" || echo -e "${GREEN}✅ No uvicorn processes to clean up${NC}"

# Clean up any remaining Next.js processes
echo -e "${YELLOW}🧹 Cleaning up any remaining Next.js processes...${NC}"
pkill -f "next-server" 2>/dev/null && echo -e "${GREEN}✅ Cleaned up Next.js processes${NC}" || echo -e "${GREEN}✅ No Next.js processes to clean up${NC}"

echo -e "\n${GREEN}🎉 All Support Flow services stopped!${NC}" 