#!/bin/bash

rm -rf build/ dist/
find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -prune -exec rm -rf {} +

echo "Cleaned previous build artifacts."
