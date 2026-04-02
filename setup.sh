#!/bin/bash
# Quick setup script — run this from the project root
echo "=== Performance Audit Tool — Setup ==="

echo ""
echo "Step 1: Installing Target API dependencies..."
cd target-api && pip install -r requirements.txt -q && cd ..

echo "Step 2: Installing Manager API dependencies..."
cd manager-api && pip install -r requirements.txt -q && cd ..

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Now open 3 terminal windows and run:"
echo ""
echo "  Terminal 1 (Target API):"
echo "    cd target-api && uvicorn main:app --port 8000 --reload"
echo ""
echo "  Terminal 2 (Manager API):"
echo "    cd manager-api && uvicorn main:app --port 8001 --reload"
echo ""
echo "  Terminal 3 (Dashboard):"
echo "    cd dashboard && npm start"
echo ""
echo "  Then open: http://localhost:3000"
echo ""
echo "  Verify Target API:  http://localhost:8000/health"
echo "  Verify Manager API: http://localhost:8001/docs"
