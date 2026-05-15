#!/bin/bash

# ===============================
# Configuration
# ===============================
PYTHON_CMD="python3"

if [ -n "$1" ]; then
    PYTHON_CMD="$1"
fi

VENV_DIR=".venv"

# ===============================
# Check Python
# ===============================
if ! command -v "$PYTHON_CMD" &> /dev/null; then
    echo "Python command \"$PYTHON_CMD\" not found. Please install Python 3.9+ and ensure it is on PATH."
    exit 1
fi

# ===============================
# Create virtual environment
# ===============================
if [ -d "$VENV_DIR/bin/activate" ]; then
    echo ".venv already exists. Skipping creation."
else
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo "Virtual environment created at .venv."
fi

# ===============================
# Set pip path
# ===============================
PIP_PATH=""
if [ -f "$VENV_DIR/bin/pip" ]; then
    PIP_PATH="$VENV_DIR/bin/pip"
fi

if [ -z "$PIP_PATH" ]; then
    echo "pip executable not found in .venv. Please check the environment."
    exit 1
fi

# ===============================
# Upgrade pip
# ===============================
echo "Upgrading pip in the virtual environment..."
"$PIP_PATH" install --upgrade pip

# ===============================
# Install dependencies
# ===============================
echo "Installing required packages..."

"$PIP_PATH" install openai python-dotenv pydantic requests pyyaml pandas numpy scikit-learn matplotlib seaborn tqdm

echo
echo "==============================="
echo "Setup complete!"
echo "Activate the environment with:"
echo "    source ./.venv/bin/activate"
echo "==============================="