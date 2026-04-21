#!/usr/bin/env python3
"""
Generate openapi.json from the FastAPI app and patch it for orval compatibility.

FastAPI 0.100+ uses OpenAPI 3.1 which encodes binary file uploads as:
  { "type": "string", "contentMediaType": "application/octet-stream" }

Orval doesn't understand contentMediaType and generates `string` instead of `Blob`.
This script rewrites those fields to use the OpenAPI 3.0-style:
  { "type": "string", "format": "binary" }

Usage (from repo root):
  uv run python scripts/generate-openapi.py
"""
import json
import sys
from pathlib import Path

repo_root = Path(__file__).parent.parent
backend_dir = repo_root / "backend"
output_path = repo_root / "frontend" / "openapi.json"

# Add backend to path so we can import the app
sys.path.insert(0, str(backend_dir))

from app.main import app  # noqa: E402

schema = app.openapi()

# Patch contentMediaType -> format: binary for orval compatibility
schemas = schema.get("components", {}).get("schemas", {})
for s in schemas.values():
    for prop in s.get("properties", {}).values():
        if prop.get("type") == "string" and "contentMediaType" in prop:
            prop["format"] = "binary"
            del prop["contentMediaType"]

output_path.write_text(json.dumps(schema, indent=2) + "\n")
print(f"Wrote {output_path}")
