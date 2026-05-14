#!/bin/bash
# SeismoSense — start the Flask backend
echo "Installing dependencies..."
pip install -r backend/requirements.txt --break-system-packages -q

echo "Starting SeismoSense API on http://localhost:8000"
cd backend && python api.py
