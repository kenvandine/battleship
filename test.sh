#!/bin/bash
set -e

# Ensure we are in the root of the repo
cd "$(dirname "$0")"

# Create a virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate the virtual environment
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r client/requirements.txt -r server/requirements.txt pytest coverage > /dev/null

# Run tests
echo "Running tests..."
pytest server/tests/test_server.py client/tests/test_client.py
