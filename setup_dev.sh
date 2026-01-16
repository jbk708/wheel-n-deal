#!/bin/bash

# Setup development environment for Wheel-n-Deal

set -e

echo "Setting up development environment for Wheel-n-Deal..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "uv is not installed. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.local/bin/env
fi

echo "uv version: $(uv --version)"

# Check Python version
python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
required_version="3.12"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Warning: Python version $python_version detected. Python 3.12+ is recommended."
fi

echo "Python version $python_version detected."

# Navigate to backend directory
cd backend

# Install dependencies with uv
echo "Installing dependencies..."
uv sync

# Install pre-commit hooks
echo "Installing pre-commit hooks..."
uv run pre-commit install

# Setup environment variables
cd ..
echo "Setting up environment variables..."
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Please edit the .env file with your configuration."
fi

echo ""
echo "Development environment setup complete!"
echo ""
echo "Commands (run from backend/ directory):"
echo "  uv run uvicorn main:app --reload  # Start API server"
echo "  uv run pytest                      # Run tests"
echo "  uv run ruff check . --fix          # Lint and fix"
echo "  uv run ruff format .               # Format code"
echo "  uv run ty check                    # Type check"
echo ""
echo "Happy coding!"
