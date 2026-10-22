"""Loopback-only controller. Run the installed copy using launchd, never as CGI."""
import copy
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

from core.catalog import PRESETS
from core.rules import domain_roots, hostnames_for, is_active, make_rule, normalize_domain, validate_rule
from .backend import atomic_write

PORT = 8765
DATA = Path('/Library/Application Support/WebsiteBlocker')
WEB = Path(__file__).parent / 'web'


def validate(state):
    if not isinstance(state, dict) or state.get('version') != 1:
        raise ValueError('Invalid settings version')
    if type(state.get('paused')) is not bool or not isinstance(state.get('rules'), list) or len(state['rules']) > 200:
        raise ValueError('Invalid settings or too many rules (maximum 200)')
    seen = set()
    for rule in state['rules']:
        validate_rule(rule)
        if rule['mode'] == 'timer':
            deadline = rule.get('expires')
            if type(deadline) not in (int, float) or not 0 < deadline < 1e12:
                raise ValueError('Invalid timer deadline')
        if rule['domain'] in seen:
            raise ValueError('Duplicate domain')
        seen.add(rule['domain'])
    return state


def active(rule, now):
    if rule['mode'] == 'timer':
        return rule.get('enabled', True) and now < rule['expires']
    return is_active(rule, now=now)


class Controller:
    def __init__(self, directory, backend):
        self.directory = Path(directory)
        self.path = self.directory / 'mac-settings.json'
        self.backend = backend
        self.lock = threading.RLock()
        self.state = validate(json.loads(self.path.read_text())) if self.path.exists() else {'version': 1, 'paused': False, 'rules': []}
        self.health = {'ok': False, 'error': 'Starting protection', 'updated': None}

    def enforce(self):
        with self.lock:
            roots, names = set(), set()
            if not self.state['paused']:
                for rule in self.state['rules']:
                    if active(rule, time.time()):
                        roots.update(domain_roots(rule))
                        names.update(hostnames_for(rule['domain'], rule.get('include_related', True)))
            try:
                self.backend.apply(roots, names)
                self.health = {'ok': True, 'error': '', 'updated': time.time(), 'domains': len(roots)}
            except Exception as error:
                logging.exception('Enforcement failed')
                self.health = {'ok': False, 'error': str(error), 'updated': time.time()}

    def snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.state)
            for rule in result['rules']:
                rule['active'] = not result['paused'] and active(rule, time.time())
            result.update(health=copy.deepcopy(self.health), presets=PRESETS,
                          timezone=time.tzname[time.localtime().tm_isdst], now=time.time())
            return result

    def change(self, action, payload):
        if not isinstance(payload, dict):
            raise ValueError('Expected a JSON object')
        with self.lock:
            state = copy.deepcopy(self.state)
            if action == 'pause':
                if type(payload.get('paused')) is not bool:
                    raise ValueError('paused must be true or false')
                state['paused'] = payload['paused']
            elif action == 'remove':
                ident = payload.get('id')
                if not any(r['id'] == ident for r in state['rules']):
                    raise ValueError('Rule no longer exists')
                state['rules'] = [r for r in state['rules'] if r['id'] != ident]
            elif action == 'toggle':
                if type(payload.get('enabled')) is not bool:
                    raise ValueError('enabled must be true or false')
                rule = next((r for r in state['rules'] if r['id'] == payload.get('id')), None)
                if rule is None:
                    raise ValueError('Rule no longer exists')
                if rule['mode'] == 'timer' and payload['enabled'] and rule['expires'] <= time.time():
                    raise ValueError('Timer expired. Add the domain again to start a new timer.')
                rule['enabled'] = payload['enabled']
            elif action == 'add':
                preset = payload.get('preset')
                if preset is not None and preset not in PRESETS:
                    raise ValueError('Unknown preset')
                domains = PRESETS[preset] if preset else [normalize_domain(payload.get('domain'))]
                mode = payload.get('mode', 'forever')
                extra = {}
                if mode == 'timer':
                    minutes = payload.get('minutes')
                    if type(minutes) is not int or not 1 <= minutes <= 525600:
                        raise ValueError('Choose 1 to 525600 minutes')
                    extra = {'duration': minutes * 60, 'expires': time.time() + minutes * 60}
                elif mode == 'schedule':
                    extra = {key: payload.get(key) for key in ('start', 'end', 'days')}
                for domain in domains:
                    rule = make_rule(domain, mode, **extra)
                    state['rules'] = [r for r in state['rules'] if r['domain'] != rule['domain']]
                    state['rules'].append(rule)
            else:
                raise ValueError('Unknown action')
            validate(state)
            atomic_write(self.path, json.dumps(state, allow_nan=False).encode())
            self.state = state
            self.enforce()
            return self.snapshot()


def handler(controller, token_hash, public_url=None):
    origins = {'http://127.0.0.1:%d' % PORT, 'http://localhost:%d' % PORT}
    if public_url:
        origins.add(public_url)
    hosts = {urlsplit(origin).netloc for origin in origins}
    assets = {'/': ('index.html', 'text/html; charset=utf-8'),
              '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
              '/style.css': ('style.css', 'text/css; charset=utf-8'),
              '/manifest.webmanifest': ('manifest.webmanifest', 'application/manifest+json'),
              '/icon.svg': ('icon.svg', 'image/svg+xml')}

    class Handler(BaseHTTPRequestHandler):
        server_version = 'WebsiteBlocker'
        timeout = 5

        def log_message(self, *_):
            pass  # No tokens, request bodies, or sensitive URLs in access logs.

        def reply(self, code, data, content_type='application/json'):
            if isinstance(data, dict):
                data = json.dumps(data, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(data)

        def allowed(self, auth=False):
            if self.headers.get('Host') not in hosts:
                self.reply(403, {'error': 'Unrecognized host; configure the exact phone URL on the Mac'})
                return False
            origin = self.headers.get('Origin')
            if origin and origin not in origins:
                self.reply(403, {'error': 'Origin not allowed'})
                return False
            if auth:
                value = self.headers.get('Authorization', '')
                if not value.startswith('Bearer ') or not hmac.compare_digest(hashlib.sha256(value[7:].encode()).hexdigest(), token_hash):
                    self.reply(401, {'error': 'Enter the control key shown on your Mac'})
                    return False
            return True

        def do_GET(self):
            path = urlsplit(self.path).path
            if not self.allowed(auth=path.startswith('/api/')):
                return
            if path == '/api/status':
                self.reply(200, controller.snapshot())
            elif path in assets:
                name, mime = assets[path]
                self.reply(200, (WEB / name).read_bytes(), mime)
            else:
                self.reply(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.allowed(auth=True):
                return
            path = urlsplit(self.path).path
            if path not in {'/api/add', '/api/remove', '/api/toggle', '/api/pause'}:
                self.reply(404, {'error': 'Not found'})
                return
            try:
                if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('Use application/json with Content-Length')
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192:
                    self.reply(413, {'error': 'Request too large or empty'})
                    return
                payload = json.loads(self.rfile.read(size))
                self.reply(200, controller.change(path.split('/')[-1], payload))
            except (ValueError, TypeError, KeyError) as error:
                self.reply(400, {'error': str(error)})
            except OSError:
                logging.exception('Settings write failed')
                self.reply(500, {'error': 'Could not save settings; check service logs on the Mac'})
    return Handler


def serve(controller, token_hash, public_url=None, stop=None):
    stop = stop or threading.Event()
    def worker():
        while not stop.is_set():
            controller.enforce()
            stop.wait(3)
    thread = threading.Thread(target=worker, daemon=True)
    # Bind before starting the worker, so two instances cannot both enforce.
    server = HTTPServer(('127.0.0.1', PORT), handler(controller, token_hash, public_url))
    thread.start()
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        thread.join(25)
