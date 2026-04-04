#!/bin/bash
echo ""
echo " ============================================"
echo "  ARIA - Build Script for macOS (.app)"
echo " ============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found. Install from python.org or: brew install python"
    exit 1
fi

echo "[1/3] Installing dependencies..."
pip3 install customtkinter pyinstaller --quiet

echo "[2/3] Building ARIA.app (this takes ~60 seconds)..."
pyinstaller --onefile --windowed --name ARIA \
    --hidden-import customtkinter \
    --collect-all customtkinter \
    aria.py

echo "[3/3] Done!"
echo ""
if [ -f "dist/ARIA" ] || [ -d "dist/ARIA.app" ]; then
    echo " SUCCESS! Your ARIA app is ready in the dist/ folder."
    echo " Double-click to launch — no installation needed!"
    open dist/
else
    echo " Build may have failed. Check output above."
fi
