#!/usr/bin/env python3
"""
Quick script to remove duplicate model definition from routes.py
"""

# Read the file with UTF-8 encoding
with open('routes.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove lines 2196-2197 (1-indexed) which contain the duplicate model definition
# In 0-indexed, that's lines 2195-2196
lines = lines[:2195] + lines[2197:]

# Write back with UTF-8 encoding
with open('routes.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Successfully removed duplicate model definition from routes.py") 