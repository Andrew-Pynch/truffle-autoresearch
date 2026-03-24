"""Server startup helper."""

from __future__ import annotations

from truffle_autoresearch.config.paths import DEFAULT_SERVER_PORT


def start_server(host: str = "0.0.0.0", port: int | None = None) -> None:
    """Start the FastAPI control server with uvicorn.

    Args:
        host: Bind address.
        port: Port number. Reads from fleet config if not given,
              falls back to DEFAULT_SERVER_PORT.
    """
    import uvicorn

    if port is None:
        try:
            from truffle_autoresearch.config.fleet import load_fleet_config

            fleet = load_fleet_config()
            port = fleet.host.port
        except Exception:
            port = DEFAULT_SERVER_PORT

    print(f"Starting AutoResearch Control Server on {host}:{port}")
    uvicorn.run(
        "truffle_autoresearch.server.app:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    start_server()
