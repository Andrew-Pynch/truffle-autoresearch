"""FastAPI control server for coordinating experiments across the fleet.

Replaces v1's standalone control-server/server.py with a proper module
that can be started via 'autoresearch dashboard' or imported for testing.
"""

from fastapi import FastAPI

app = FastAPI(title="AutoResearch Control Server", version="0.1.0")


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
