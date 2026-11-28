"""Serve the correction application through a Docker-published port.

The application keeps its loopback bind and Host/Origin checks. The relay only
accepts the bridge gateway, which is where Docker delivers published connections,
so other containers on the bridge cannot reach the application through it.
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import threading
from pathlib import Path


def default_gateway(route_table: Path = Path("/proc/net/route")) -> str:
    """Return the IPv4 default gateway of this container."""
    for line in route_table.read_text(encoding="ascii").splitlines()[1:]:
        fields = line.split()
        if fields[1] == "00000000":
            return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    raise ValueError("Review relay requires a default gateway")


def _pump(source: socket.socket, target: socket.socket) -> None:
    try:
        while data := source.recv(65536):
            target.sendall(data)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _relay(client: socket.socket, target_port: int) -> None:
    with client:
        try:
            upstream = socket.create_connection(("127.0.0.1", target_port))
        except OSError as exc:
            print(f"Review relay could not reach the application: {exc}", file=sys.stderr)
            return
        with upstream:
            reply = threading.Thread(target=_pump, args=(upstream, client), daemon=True)
            reply.start()
            _pump(client, upstream)
            reply.join()


def serve_relay(listener: socket.socket, *, target_port: int, allowed_peer: str) -> None:
    """Forward connections from ``allowed_peer`` to the loopback application."""
    while True:
        client, peer = listener.accept()
        if peer[0] != allowed_peer:
            print(f"Review relay refused connection from {peer[0]}", file=sys.stderr)
            client.close()
            continue
        threading.Thread(target=_relay, args=(client, target_port), daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True, help="Port the browser opens")
    parser.add_argument("--relay-port", type=int, required=True, help="Published container port")
    args = parser.parse_args()
    from tools.review_correction.server import create_server

    try:
        allowed_peer = default_gateway()
        server = create_server(args.handoff, port=args.port)
        listener = socket.create_server(("0.0.0.0", args.relay_port))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    threading.Thread(
        target=serve_relay,
        args=(listener,),
        kwargs={"target_port": args.port, "allowed_peer": allowed_peer},
        daemon=True,
    ).start()
    print(f"Correction review: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
