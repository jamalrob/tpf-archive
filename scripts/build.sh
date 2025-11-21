#!/bin/bash
cd "$(dirname "$0")/.."
python3 converter/convert_forum.py
cp -r build/static_archive/* public/