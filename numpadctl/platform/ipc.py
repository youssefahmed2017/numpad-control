"""The connection between the background service and the settings window.

Messages are JSON lines either way. Linux uses a Unix socket that only this
user can open. Windows has no such sockets for asyncio, so it uses a TCP
connection on 127.0.0.1 with a random key the client must send first; the key
and port are in a file only this user can read.
"""

import asyncio
import json
import os
import secrets
import socket

from . import IS_WINDOWS, paths

SOCKET_NAME = "numpad-control.sock"
TCP_INFO_NAME = "numpad-control.port"


def _use_tcp():
    return IS_WINDOWS or os.environ.get("NUMPADCTL_IPC") == "tcp"  # tcp is also testable on Linux


def socket_path():
    return paths.runtime_dir() / SOCKET_NAME


def _tcp_info_path():
    return paths.runtime_dir() / TCP_INFO_NAME


async def start_server(handle_client):
    """Start listening; handle_client(reader, writer) is called per client."""
    if not _use_tcp():
        path = socket_path()
        path.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(handle_client, path=str(path))
        os.chmod(path, 0o600)
        return server

    key = secrets.token_hex(16)

    async def checked(reader, writer):
        try:
            first = await asyncio.wait_for(reader.readline(), 5)
        except (asyncio.TimeoutError, ConnectionError):
            first = b""
        if first.strip() != key.encode():
            writer.close()
            return
        await handle_client(reader, writer)

    server = await asyncio.start_server(checked, host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    info = _tcp_info_path()
    info.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(info, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"port": port, "key": key}, f)
    return server


def stop_server():
    for path in (socket_path(), _tcp_info_path()):
        path.unlink(missing_ok=True)


def connect():
    """A connected, blocking socket to the service (raises OSError if it isn't running)."""
    if not _use_tcp():
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(socket_path()))
        except OSError:
            sock.close()
            raise
        return sock
    try:
        with open(_tcp_info_path()) as f:
            info = json.load(f)
    except (OSError, ValueError) as e:
        raise ConnectionRefusedError("the service isn't running") from e
    sock = socket.create_connection(("127.0.0.1", info["port"]), timeout=2)
    sock.settimeout(None)
    sock.sendall(info["key"].encode() + b"\n")
    return sock
