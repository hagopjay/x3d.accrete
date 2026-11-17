#!/usr/bin/env python3
"""Local Accretion Observatory. No cloud runtime or model credentials are used."""
from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import secrets
import sys
from urllib.parse import parse_qs, urlsplit
import webbrowser

from accretion.codec import canonical, strict_json
from accretion.world import WorldStore, Conflict, AdmissionRefused, wrap_scene
from accretion.mcp_adapter import validate_scene

ROOT = Path(__file__).resolve().parent


def owner_key(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / 'owner.key'
    if not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='ascii') as stream:
            stream.write(secrets.token_hex(32))
    if os.name == 'posix' and path.stat().st_mode & 0o077:
        os.chmod(path, 0o600)   # repair a loose pre-existing key rather than trust it
    key = path.read_text(encoding='ascii').strip()
    if not re.fullmatch('[0-9a-f]{64}', key):
        raise ValueError('Invalid local author capability file')
    return key


class Handler(SimpleHTTPRequestHandler):
    timeout = 15   # seconds per socket operation: stalled or short-bodied connections cannot pin a thread forever
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT/'web'), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "frame-ancestors 'none'")
        super().end_headers()

    def log_message(self, *_):
        pass

    def host_ok(self):
        # DNS-rebinding guard: only the literal loopback names on our own port are answered.
        return self.headers.get('Host', '') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def list_directory(self, path):
        self.send_error(404, 'No directory listing')
        return None

    def do_HEAD(self):
        if not self.host_ok():
            return self.send_error(403, 'Host not allowed')
        path = urlsplit(self.path).path
        if path.startswith(('/api/', '/patches/')):
            self.send_response(200); self.send_header('Content-Length', '0'); self.end_headers()
        else:
            super().do_HEAD()

    def writer(self):
        header = self.headers.get('Authorization', '')
        return header.startswith('Bearer ') and secrets.compare_digest(header[7:].encode('utf-8'), self.server.owner_key.encode('ascii'))

    def allowed_origin(self):
        origin = self.headers.get('Origin')
        if not origin:
            return True
        try:
            parsed = urlsplit(origin)
            return parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost') and parsed.port == self.server.server_port
        except ValueError:
            return False

    def send_data(self, value, status=200, content_type='application/json; charset=utf-8', filename=None):
        data = value if isinstance(value, bytes) else canonical(value)
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(data)

    def capabilities(self):
        return {'writer': self.writer(), 'cloud_presence': False, 'actual_mcp': self.server.mcp_probe.get('status') == 'pass',
                'local_reference': True, 'model_calls': 0, 'identity_scope': 'Local author capability; no authenticated human-presence count.'}

    def do_GET(self):
        if not self.host_ok():
            self.send_data({'error': 'Host header not allowed'}, 403)
            return
        url = urlsplit(self.path)
        path = url.path
        store = self.server.store
        try:
            if path == '/api/world':
                limit = int(parse_qs(url.query).get('limit', ['512'])[0])
                result = store.world(limit)
                result['capabilities'] = self.capabilities()
                self.send_data(result)
            elif path == '/api/status':
                self.send_data({'capabilities': self.capabilities(), 'mcp_probe': self.server.mcp_probe})
            elif path == '/api/verify':
                self.send_data(store.verify())
            elif path == '/api/attempts':
                self.send_data({'attempts': store.recent_attempts()})
            elif path == '/api/export.json':
                self.send_data(store.archive(), filename='Accretion-world.json')
            elif path == '/api/export.x3d':
                self.send_data(store.export_x3d().encode(), content_type='model/x3d+xml; charset=utf-8', filename='Accretion-world.x3d')
            elif re.fullmatch(r'/api/entries/[0-9]{1,6}', path):
                self.send_data(store.detail(int(path.rsplit('/', 1)[1])))
            elif re.fullmatch(r'/patches/[0-9]{1,6}\.x3d', path):
                n = int(path.rsplit('/', 1)[1].split('.')[0])
                self.send_data(store.detail(n)['scene_x3d'].encode(), content_type='model/x3d+xml; charset=utf-8')
            elif path.startswith(('/api/', '/patches/')):
                self.send_data({'error': 'No such local resource'}, 404)
            else:
                super().do_GET()
        except KeyError:
            self.send_data({'error': 'No such patch'}, 404)
        except (ValueError, TypeError) as error:
            self.send_data({'error': str(error)}, 400)

    def do_POST(self):
        if not self.host_ok():
            self.send_data({'error': 'Host header not allowed'}, 403)
            return
        if not self.writer() or not self.allowed_origin():
            self.send_data({'error': 'A local author capability and same-origin request are required. Open the author URL printed by the server.'}, 403)
            return
        path = urlsplit(self.path).path
        if path not in ('/api/grow', '/api/submit'):
            self.send_data({'error': 'No such local action'}, 404)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 1 <= size <= 65_536:
                raise ValueError('A request must contain 1..65536 bytes of JSON')
            request = strict_json(self.rfile.read(size).decode('utf-8'))
            allowed = {'tier','expected_head','expected_tail_hash','force_mode'}
            if path == '/api/submit':
                allowed |= {'title','instruction','x3d'}
            if not isinstance(request, dict) or set(request) - allowed:
                raise ValueError('Unexpected request fields')
            if path == '/api/submit':
                candidate = {key: request.pop(key) for key in ('title','instruction','x3d')}
                candidate['generator'] = {'id': 'local-author-editor', 'version': '1', 'kind': 'manual'}
                request['candidate'] = candidate
            self.send_data(self.server.store.append(**request))
        except Conflict as error:
            self.send_data({'error': str(error), 'code': 'HEAD_CONFLICT'}, 409)
        except AdmissionRefused as error:
            self.send_data({'error': str(error), 'attempt': error.attempt}, 400)
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            self.send_data({'error': str(error) if not isinstance(error, RecursionError) else 'JSON nested too deeply'}, 400)


def make_server(store, key, port=8820):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.store = store
    server.owner_key = key
    server.mcp_probe = validate_scene(wrap_scene('<Group/>'))
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8820)
    parser.add_argument('--data', type=Path, default=ROOT/'data')
    parser.add_argument('--demo-count', type=int, default=24)
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or not 0 <= args.demo_count <= 96:
        parser.error('Port must be 1..65535; demo count must be 0..96')
    key = owner_key(args.data)
    store = WorldStore(args.data/'world.sqlite3')
    if not store.verify()['valid']:
        raise ValueError('Stored world failed verification. Preserve the data and inspect it before restarting.')
    server = make_server(store, key, args.port)
    if server.mcp_probe.get('status') == 'pass' and store.snapshot()['head'] == 0:
        for index in range(args.demo_count):
            snap = store.snapshot()
            store.append(tier=3+(index%3), expected_head=snap['head'], expected_tail_hash=snap['tail_hash'])
        if args.demo_count:
            print(f'Created {args.demo_count} authored procedural demo seeds, each admitted by local gate and pinned validators.', flush=True)
    elif server.mcp_probe.get('status') != 'pass':
        print('Pinned validator unavailable: install requirements.txt with this Python interpreter. Growth remains fail-closed.', flush=True)
    author = f'http://127.0.0.1:{args.port}/#owner={key}'
    print('Accretion Observatory — local reference edition; no model calls.', flush=True)
    print('Viewer: '+f'http://127.0.0.1:{args.port}/', flush=True)
    print('Local author URL (keep private on this machine): '+author, flush=True)
    if args.open:
        webbrowser.open(author)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
