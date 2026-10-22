"""Mac controller tests use temporary files and loopback; never modify system DNS."""
import copy
import hashlib
from http.client import HTTPConnection
from http.server import HTTPServer
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from macos.backend import Backend, DNSUDP, DNSTCP, UDPHandler, TCPHandler, dns_response, MARKER
from macos.service import Controller, handler
from macos.manage import public_origin


def query(name='random.cdn.youtube.com', kind=1):
    labels = b''.join(bytes([len(p)]) + p.encode() for p in name.split('.'))
    return struct.pack('!6H', 42, 0x100, 1, 0, 0, 0) + labels + b'\0' + struct.pack('!HH', kind, 1)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hosts = self.root / 'hosts'
        self.hosts.write_text('127.0.0.1 localhost\n10.1.1.1 office.local\n')
        self.backend = Backend(self.root, self.hosts, self.root / 'resolver', flush=False)

    def test_apply_remove_preserves_unrelated_files(self):
        original = self.hosts.read_bytes()
        self.assertTrue(self.backend.apply({'youtube.com'}, {'youtube.com'}))
        self.assertIn(MARKER, (self.root / 'resolver/youtube.com').read_text())
        self.assertIn(':: youtube.com', self.hosts.read_text())
        self.assertFalse(self.backend.apply({'youtube.com'}, {'youtube.com'}))
        (self.root / 'resolver/company.test').write_text('nameserver 10.1.1.1\n')
        self.backend.apply(set(), set())
        self.assertEqual(self.hosts.read_bytes(), original)
        self.assertTrue((self.root / 'resolver/company.test').exists())
        self.assertEqual((self.root / 'hosts-before-install.txt').read_bytes(), original)

    def test_collision_and_symlink_leave_hosts_unchanged(self):
        self.backend.apply(set(), set())
        original = self.hosts.read_bytes()
        resolver = self.root / 'resolver/youtube.com'
        resolver.write_text('nameserver 10.0.0.1')
        with self.assertRaises(OSError):
            self.backend.apply({'youtube.com'}, {'youtube.com'})
        self.assertEqual(self.hosts.read_bytes(), original)
        resolver.unlink()
        resolver.symlink_to(self.hosts)
        with self.assertRaises(OSError):
            self.backend.apply({'youtube.com'}, {'youtube.com'})
        self.assertEqual(self.hosts.read_bytes(), original)

    def test_controller_persistence_timer_and_pause(self):
        controller = Controller(self.root, self.backend)
        state = controller.change('add', {'domain': 'youtube.com', 'mode': 'timer', 'minutes': 1})
        self.assertTrue(state['health']['ok'])
        self.assertTrue(state['rules'][0]['active'])
        restarted = Controller(self.root, self.backend)
        with patch('macos.service.time.time', return_value=time.time() + 61):
            restarted.enforce()
            self.assertFalse(restarted.snapshot()['rules'][0]['active'])
            self.assertFalse((self.root / 'resolver/youtube.com').exists())
        controller.change('add', {'domain': 'epicgames.com'})
        controller.change('pause', {'paused': True})
        self.assertNotIn('WEBSITE-BLOCKER', self.hosts.read_text())
        controller.change('pause', {'paused': False})
        self.assertIn('epicgames.com', self.hosts.read_text())

    def test_invalid_payload_never_replaces_state(self):
        controller = Controller(self.root, self.backend)
        for payload in ({'domain':'x.com\n127.0.0.1 foo.com'}, {'domain':'x.com', 'mode':'timer','minutes':True},
                        {'domain':'x.com','mode':'schedule','days':[7],'start':'09:00','end':'17:00'},
                        {'preset':'nope'}, {'domain':'x.com','mode':'timer','minutes':float('nan')}):
            with self.assertRaises((ValueError, TypeError)):
                controller.change('add',payload)
        self.assertEqual(controller.snapshot()['rules'], [])
        self.assertFalse(controller.path.exists())

    def test_backend_error_reported_and_retried(self):
        controller = Controller(self.root, self.backend)
        with patch.object(self.backend, 'apply', side_effect=OSError('disk failure')):
            with self.assertLogs(level='ERROR'):
                result = controller.change('add', {'domain':'youtube.com'})
        self.assertFalse(result['health']['ok'])
        self.assertIn('disk failure', result['health']['error'])
        controller.enforce()
        self.assertTrue(controller.health['ok'])

    def test_corrupt_settings_do_not_clear_existing_blocks(self):
        self.backend.apply({'youtube.com'}, {'youtube.com'})
        (self.root/'mac-settings.json').write_text('{broken')
        with self.assertRaises(ValueError):
            Controller(self.root, self.backend)
        self.assertTrue((self.root/'resolver/youtube.com').exists())


class DNSTests(unittest.TestCase):
    def test_answers_ipv4_ipv6_and_https_queries(self):
        for kind in (1, 28, 65):
            response = dns_response(query(kind=kind))
            self.assertEqual(struct.unpack('!6H', response[:12]), (42, 0x8503, 1, 0, 0, 0))
            self.assertEqual(response[12:], query(kind=kind)[12:])

    def test_malformed_packets(self):
        for packet in (b'', b'\0'*12, query()[:15], query()[:12]+b'\xc0\x0c\0\x01\0\x01',
                       struct.pack('!6H',42,0x8100,1,0,0,0)+query()[12:]):
            self.assertIsNone(dns_response(packet))

    def test_real_udp_and_tcp(self):
        for factory, handler_type in ((DNSUDP, UDPHandler), (DNSTCP, TCPHandler)):
            server = factory(('127.0.0.1',0), handler_type)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                if factory is DNSUDP:
                    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as client:
                        client.settimeout(2); client.sendto(query(),server.server_address)
                        response=client.recv(4096)
                else:
                    with socket.create_connection(server.server_address,timeout=2) as client:
                        client.sendall(struct.pack('!H',len(query()))+query())
                        stream=client.makefile('rb')
                        length=struct.unpack('!H',stream.read(2))[0]; response=stream.read(length)
                self.assertEqual(response,dns_response(query()))
            finally:
                server.shutdown(); server.server_close(); thread.join()


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name); (root/'hosts').write_text('127.0.0.1 localhost\n')
        self.controller=Controller(root,Backend(root,root/'hosts',root/'resolver',flush=False))
        self.key='test-key-not-a-production-secret'
        self.server=HTTPServer(('127.0.0.1',0),handler(self.controller,hashlib.sha256(self.key.encode()).hexdigest(),'https://mac.example.ts.net'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.addCleanup(self.cleanup_server)

    def cleanup_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self,path='/api/status',body=None,auth=True,host='127.0.0.1:8765',origin=None):
        client=HTTPConnection(*self.server.server_address,timeout=3)
        headers={'Host':host}
        if auth: headers['Authorization']='Bearer '+self.key
        if origin: headers['Origin']=origin
        if body is not None: headers['Content-Type']='application/json'
        client.request('POST' if body is not None else 'GET',path,body=json.dumps(body) if body is not None else None,headers=headers)
        response=client.getresponse(); data=response.read(); status=response.status; client.close()
        return status,data

    def test_auth_origin_host_and_no_public_status(self):
        self.assertEqual(self.request(auth=False)[0],401)
        self.assertEqual(self.request(origin='https://evil.test')[0],403)
        self.assertEqual(self.request(host='evil.test')[0],403)
        self.assertEqual(self.request(host='mac.example.ts.net',origin='https://mac.example.ts.net')[0],200)
        self.assertEqual(self.request('/api/add',{'domain':'youtube.com'},auth=False)[0],401)
        self.assertEqual(self.controller.snapshot()['rules'],[])

    def test_add_toggle_remove_and_static_assets(self):
        code,data=self.request('/api/add',{'domain':'youtube.com'})
        self.assertEqual(code,200); state=json.loads(data); ident=state['rules'][0]['id']
        self.assertTrue(state['health']['ok'])
        self.assertEqual(self.request('/api/toggle',{'id':ident,'enabled':False})[0],200)
        self.assertEqual(self.request('/api/remove',{'id':ident})[0],200)
        self.assertEqual(self.controller.snapshot()['rules'],[])
        for path in ('/','/app.js','/style.css','/manifest.webmanifest','/icon.svg'):
            self.assertEqual(self.request(path,auth=False)[0],200)
        self.assertEqual(self.request('/../manage.py',auth=False)[0],404)
        self.assertEqual(self.request('/api/add',[])[0],400)

    def test_configured_url_is_private_https_only(self):
        self.assertEqual(public_origin('https://mac.example.ts.net/'),'https://mac.example.ts.net')
        for url in ('http://mac.example.ts.net','https://evil.test','https://mac.example.ts.net/evil','https://mac.example.ts.net@evil.test'):
            with self.assertRaises(ValueError): public_origin(url)


if __name__=='__main__': unittest.main()
