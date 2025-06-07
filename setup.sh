#!/bin/bash

echo "🛠️  Setting up Support Flow dependencies..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Setup Backend
echo -e "\n${YELLOW}📦 Setting up Backend (Python)...${NC}"
cd 02-backend

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    print_warning "Virtual environment not found. Creating one..."
    python3 -m venv venv
fi

# Activate virtual environment and install dependencies
source venv/bin/activate
print_status "Activated virtual environment"

# Upgrade pip
pip install --upgrade pip

# Install requirements
print_status "Installing Python dependencies..."
pip install -r requirements.txt

# Verify key imports and simplified backend structure
python -c "
import fastapi, uvicorn, vertexai
from google.cloud import firestore
print('✅ Core backend dependencies verified')
" 2>/dev/null && print_status "Backend dependencies verified" || print_error "Backend dependency verification failed"

# Verify main.py exists
if [ -f "main.py" ]; then
    print_status "Simplified backend main.py found"
else
    print_error "main.py not found in 02-backend directory"
fi

deactivate

# Setup Processing Service (Optional)
if [ -d "../03-processing" ]; then
    echo -e "\n${YELLOW}📦 Setting up Processing Service (Python) - Optional...${NC}"
    cd ../03-processing

    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        print_warning "Processing service virtual environment not found. Creating one..."
        python3 -m venv venv
    fi

    # Activate virtual environment and install dependencies
    source venv/bin/activate
    print_status "Activated processing service virtual environment"

    # Upgrade pip
    pip install --upgrade pip

    # Install requirements
    if [ -f "requirements.txt" ]; then
        print_status "Installing processing service dependencies..."
        pip install -r requirements.txt

        # Verify key imports
        python -c "import fastapi, uvicorn; print('✅ Core processing service dependencies verified')" 2>/dev/null && print_status "Processing service dependencies verified" || print_error "Processing service dependency verification failed"
    else
        print_warning "No requirements.txt found for processing service"
    fi

    deactivate
    cd ..
else
    print_warning "Processing service directory (03-processing) not found - skipping"
fi

# Setup Frontend
echo -e "\n${YELLOW}📦 Setting up Frontend (Node.js)...${NC}"
cd 01-frontend

# Check if node_modules exists, if not run npm install
if [ ! -d "node_modules" ]; then
    print_warning "Node modules not found. Installing..."
    npm install
else
    print_status "Node modules found. Updating dependencies..."
    npm install
fi

# Verify Next.js installation
npx next --version >/dev/null 2>&1 && print_status "Next.js verified" || print_error "Next.js verification failed"

# Test lint (should show linting results, not errors)
print_status "Testing lint command..."
npm run lint --silent >/dev/null 2>&1 && print_status "Lint command working" || print_warning "Lint found issues (this is normal)"

echo -e "\n${GREEN}🚀 Setup complete! You can now use:${NC}"
echo "  • npm run dev (in 01-frontend for frontend)"
echo "  • npm run lint (in 01-frontend for linting)"
echo "  • python main.py (in 02-backend with venv activated for backend)"
echo "  • uvicorn main:app --reload --port 8000 (in 02-backend with venv activated)"
if [ -d "03-processing" ]; then
    echo "  • uvicorn main:app --port 8080 (in 03-processing with venv activated for processing service)"
fi
echo "  • ./start.sh (to start all services)"

cd .. 