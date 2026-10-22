"""macOS enforcement. Only files bearing our marker are removed or replaced."""
import os
from pathlib import Path
import socketserver
import struct
import subprocess
import tempfile

from core.hosts import render
from core.rules import normalize_domain

MARKER = "# WebsiteBlocker macOS managed resolver\n"
DNS_PORT = 5354


def atomic_write(path, data, mode=0o600):
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix=".wb-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Backend:
    def __init__(self, data_dir, hosts="/etc/hosts", resolver="/etc/resolver", flush=True):
        self.data_dir = Path(data_dir)
        # /etc is a symlink on macOS; resolve to preserve the real file location.
        self.hosts = Path(hosts).resolve()
        self.resolver = Path(resolver)
        self.flush = flush

    def apply(self, roots, hostnames):
        fresh = not self.resolver.exists()
        self.resolver.mkdir(mode=0o755, parents=True, exist_ok=True)
        if fresh:
            self.resolver.chmod(0o755)  # mDNSResponder runs as an unprivileged user.
        desired = {}
        for root in roots:
            if normalize_domain(root) != root or "/" in root:
                raise ValueError("Invalid resolver domain")
            desired[root] = (MARKER + "nameserver 127.0.0.1\nport %d\n" % DNS_PORT).encode()
        # Detect collisions before changing anything; never overwrite VPN/admin resolvers.
        for root in desired:
            path = self.resolver / root
            if path.is_symlink() or (path.exists() and not path.read_bytes().startswith(MARKER.encode())):
                raise OSError("Existing resolver conflicts with rule: " + root)
        changed = False
        for root, content in desired.items():
            path = self.resolver / root
            if not path.exists() or path.read_bytes() != content:
                atomic_write(path, content, 0o644)
                changed = True
        for path in self.resolver.iterdir():
            if path.is_file() and not path.is_symlink() and path.name not in desired:
                if path.read_bytes().startswith(MARKER.encode()):
                    path.unlink()
                    changed = True
        current = self.hosts.read_bytes()
        updated = render(current.decode("utf-8", "surrogateescape"), hostnames).replace("\r\n", "\n").encode("utf-8", "surrogateescape")
        if current != updated:
            backup = self.data_dir / "hosts-before-install.txt"
            if not backup.exists():
                atomic_write(backup, current)
            atomic_write(self.hosts, updated, self.hosts.stat().st_mode & 0o777)
            changed = True
        if changed and self.flush:
            for command in (["/usr/bin/dscacheutil", "-flushcache"], ["/usr/bin/killall", "-HUP", "mDNSResponder"]):
                subprocess.run(command, check=True, capture_output=True, timeout=10)
        return changed


def dns_response(packet):
    """Answer a single uncompressed DNS question with NXDOMAIN; never forward.

    Only blocked suffixes are routed here by macOS. Reject malformed packets,
    responses, non-query opcodes and oversized names. UDP and TCP use the same parser.
    """
    if len(packet) < 17:
        return None
    ident, flags, questions, _, _, _ = struct.unpack("!6H", packet[:12])
    if flags & 0xF800 or questions != 1:
        return None
    pos = 12
    while pos < len(packet):
        length = packet[pos]
        pos += 1
        if length == 0:
            break
        if length > 63 or pos + length > len(packet):
            return None
        pos += length
    else:
        return None
    if pos - 12 > 255 or pos + 4 > len(packet):
        return None
    return struct.pack("!6H", ident, 0x8403 | (flags & 0x0100), 1, 0, 0, 0) + packet[12:pos + 4]


class DNSUDP(socketserver.UDPServer):
    allow_reuse_address = True


class UDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        response = dns_response(self.request[0])
        if response:
            self.request[1].sendto(response, self.client_address)


class DNSTCP(socketserver.TCPServer):
    allow_reuse_address = True


class TCPHandler(socketserver.StreamRequestHandler):
    timeout = 2

    def handle(self):
        header = self.rfile.read(2)
        if len(header) != 2:
            return
        size = struct.unpack("!H", header)[0]
        if size > 4096:
            return
        response = dns_response(self.rfile.read(size))
        if response:
            self.wfile.write(struct.pack("!H", len(response)) + response)
