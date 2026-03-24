"""
AXL Silo — Entry Point

Usage:
    python run.py                       # Start the server on :7000
    python run.py --port 8000           # Custom port
    python run.py --config config.yaml  # Load workspace config on start
"""

import argparse
import logging
from api.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="AXL Silo — The Particle Accelerator for LLMs")
    parser.add_argument("--port", type=int, default=7000, help="Server port")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()

    app = create_app()

    print(f"""
    ╔═══════════════════════════════════════════╗
    ║          AXL SILO — v0.1.0                ║
    ║  The Particle Accelerator for LLMs        ║
    ║                                           ║
    ║  http://localhost:{args.port}                  ║
    ║  WebSocket: ws://localhost:{args.port}/ws       ║
    ║                                           ║
    ║  axlprotocol.org                          ║
    ╚═══════════════════════════════════════════╝
    """)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
