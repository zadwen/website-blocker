#!/usr/bin/env python3
"""Explicit local administrator setup/recovery. No shell execution from the API."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import secrets
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macos.backend import Backend, DNSUDP, DNSTCP, UDPHandler, TCPHandler, DNS_PORT, atomic_write
from macos.service import Controller, DATA, serve

LABEL = 'com.zadwen.websiteblocker'
PLIST = Path('/Library/LaunchDaemons/' + LABEL + '.plist')
CODE = DATA / 'app'
OPTIONS = DATA / 'controller.json'
APP = Path('/Applications/Website Blocker.app')


def secure_python():
    executable = Path(sys.executable).resolve()
    for target in (executable, Path(sys.prefix).resolve()):
        for path in (target, *target.parents):
            stat = path.stat()
            if stat.st_uid != 0 or stat.st_mode & 0o022:
                raise SystemExit('Install a root-owned Python 3.11+ from python.org. Homebrew/user-writable runtimes cannot run this root service safely.')
    return str(executable)


def public_origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.ts.net')
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('Use the exact https://your-mac.your-tailnet.ts.net URL printed by tailscale serve')
    return 'https://' + parsed.netloc


def restart():
    subprocess.run(['/bin/launchctl', 'bootout', 'system/' + LABEL], capture_output=True)
    subprocess.run(['/bin/launchctl', 'bootstrap', 'system', str(PLIST)], check=True)


def install():
    python = secure_python()
    if ROOT == CODE:
        raise SystemExit('Install/update from your downloaded repository, not the installed copy.')
    DATA.mkdir(parents=True, mode=0o700, exist_ok=True)
    if DATA.is_symlink() or DATA.stat().st_uid != 0:
        raise SystemExit('Data directory must be a real root-owned directory.')
    os.chmod(DATA, 0o700)
    # Stop the old service before replacing its code; preserve rules and key on updates.
    subprocess.run(['/bin/launchctl', 'bootout', 'system/' + LABEL], capture_output=True)
    CODE.mkdir(mode=0o700, exist_ok=True)
    for directory in ('core', 'macos'):
        source = ROOT / directory
        if any(p.is_symlink() for p in source.rglob('*')):
            raise SystemExit('Source must not contain symlinks.')
        destination = CODE / directory
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.app'))
    if not OPTIONS.exists():
        key = secrets.token_urlsafe(32)
        atomic_write(DATA / 'control-key.txt', (key + '\n').encode())
        atomic_write(OPTIONS, json.dumps({'token_hash': hashlib.sha256(key.encode()).hexdigest(), 'public_url': None}).encode())
    plist = {'Label': LABEL, 'ProgramArguments': [python, '-I', str(CODE / 'macos/manage.py'), 'run'],
             'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10,
             'UserName': 'root', 'WorkingDirectory': str(CODE), 'Umask': 0o077,
             'StandardOutPath': str(DATA / 'service.log'), 'StandardErrorPath': str(DATA / 'service.log')}
    atomic_write(PLIST, plistlib.dumps(plist), 0o644)
    # Install a transparent browser launcher as the Mac application.
    if APP.exists():
        marker = APP / 'Contents/Info.plist'
        if not marker.exists() or plistlib.loads(marker.read_bytes()).get('CFBundleIdentifier') != LABEL + '.panel':
            raise SystemExit('An unrelated Website Blocker.app already exists; rename it first.')
        shutil.rmtree(APP)
    shutil.copytree(ROOT / 'macos/Website Blocker.app', APP)
    os.chmod(APP / 'Contents/MacOS/WebsiteBlocker', 0o755)
    restart()
    # Confirm the API answers, rather than just reporting launchctl accepted the plist.
    from urllib.request import Request, urlopen
    key = (DATA / 'control-key.txt').read_text().strip()
    for _ in range(20):
        try:
            request = Request('http://127.0.0.1:8765/api/status', headers={'Authorization': 'Bearer ' + key})
            with urlopen(request, timeout=2) as response:
                health = json.load(response)['health']
            if health['ok']:
                print('Installed. Open Website Blocker in Applications. Your control key:')
                print(key)
                return
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit('Installed, but protection is not healthy yet. Check: sudo tail -n 40 "' + str(DATA / 'service.log') + '"')


def run():
    import fcntl
    import logging
    from logging.handlers import RotatingFileHandler
    lock = open(DATA / 'service.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(DATA / 'errors.log', maxBytes=1024 * 1024, backupCount=2)])
    options = json.loads(OPTIONS.read_text())
    servers = []
    try:
        # Both transports must bind before resolver files can redirect traffic here.
        servers.append(DNSUDP(('127.0.0.1', DNS_PORT), UDPHandler))
        servers.append(DNSTCP(('127.0.0.1', DNS_PORT), TCPHandler))
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        serve(Controller(DATA, Backend(DATA)), options['token_hash'], options.get('public_url'))
    finally:
        for server in servers:
            server.server_close()
        lock.close()


def main():
    parser = argparse.ArgumentParser(description='Website Blocker macOS administration')
    parser.add_argument('command', choices=['install', 'run', 'key', 'rotate-key', 'phone-url', 'uninstall'])
    parser.add_argument('url', nargs='?')
    args = parser.parse_args()
    if sys.platform != 'darwin' or os.geteuid() != 0:
        raise SystemExit('Run this command on macOS with sudo (administrator permission).')
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11+ is required.')
    os.umask(0o077)
    if args.command == 'install':
        install()
    elif args.command == 'run':
        run()
    elif args.command == 'key':
        print((DATA / 'control-key.txt').read_text().strip())
    elif args.command in ('phone-url', 'rotate-key'):
        options = json.loads(OPTIONS.read_text())
        if args.command == 'phone-url':
            options['public_url'] = public_origin(args.url or '')
        else:
            key = secrets.token_urlsafe(32)
            options['token_hash'] = hashlib.sha256(key.encode()).hexdigest()
            atomic_write(DATA / 'control-key.txt', (key + '\n').encode())
        atomic_write(OPTIONS, json.dumps(options).encode())
        restart()
        print('Controller updated.' if args.command == 'phone-url' else 'Old key revoked. New key:\n' + key)
    elif args.command == 'uninstall':
        subprocess.run(['/bin/launchctl', 'bootout', 'system/' + LABEL], capture_output=True)
        # Remove only managed blocks, not the entire backed-up hosts file.
        Backend(DATA).apply(set(), set())
        PLIST.unlink(missing_ok=True)
        if APP.exists() and plistlib.loads((APP / 'Contents/Info.plist').read_bytes()).get('CFBundleIdentifier') == LABEL + '.panel':
            shutil.rmtree(APP)
        print('Service and blocking removed. Settings/backups retained in ' + str(DATA))


if __name__ == '__main__':
    main()
