"""WSGI entry point for shared / managed Python hosting (Hostinger "Python App", cPanel Passenger, gunicorn, uWSGI).

    startup file : passenger_wsgi.py          entry point : application
    gunicorn     : gunicorn -w 2 passenger_wsgi:application

The site itself (pages, API, payments, accounts) is the same code as `python3 server.py`; this file only lets a WSGI host call it.
Alerts are sent by the worker, which is NOT started here (a host may run several processes). Run it from a cron job instead:
    cd /path/to/app && python3 worker.py --once        (every 15 minutes)
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server as _server  # noqa: E402

_ST, _DB, _SVC = _server.build()
_HANDLER = _server.make_handler(_SVC, _ST, _server.RateLimiter())


class _Conn:
    """Just enough of a socket for http.server's handler: it reads one request and writes one response."""
    def __init__(self, raw):
        self._raw, self.out = raw, io.BytesIO()

    def makefile(self, mode='rb', *a, **k):
        return io.BytesIO(self._raw)

    def sendall(self, b):
        self.out.write(bytes(b))

    def settimeout(self, t):
        pass

    def close(self):
        pass


def application(environ, start_response):
    method = environ.get('REQUEST_METHOD', 'GET')
    target = environ.get('REQUEST_URI') or (environ.get('SCRIPT_NAME', '') + environ.get('PATH_INFO', '') + ('?' + environ['QUERY_STRING'] if environ.get('QUERY_STRING') else ''))
    if not target.startswith('/'):
        target = '/' + target
    try:
        n = int(environ.get('CONTENT_LENGTH') or 0)
    except ValueError:
        n = 0
    body = environ['wsgi.input'].read(n) if n > 0 else b''
    heads = [('Host', environ.get('HTTP_HOST') or environ.get('SERVER_NAME', 'localhost')), ('Connection', 'close')]
    if environ.get('CONTENT_TYPE'):
        heads.append(('Content-Type', environ['CONTENT_TYPE']))
    heads.append(('Content-Length', str(len(body))))
    for k, v in environ.items():
        if k.startswith('HTTP_') and k not in ('HTTP_HOST', 'HTTP_CONNECTION', 'HTTP_CONTENT_LENGTH', 'HTTP_CONTENT_TYPE', 'HTTP_TRANSFER_ENCODING'):
            heads.append((k[5:].replace('_', '-').title(), v))
    raw = ('%s %s HTTP/1.1\r\n' % (method, target)).encode('latin-1', 'replace') + b''.join(('%s: %s\r\n' % h).encode('latin-1', 'replace') for h in heads) + b'\r\n' + body
    conn = _Conn(raw)
    _HANDLER(conn, (environ.get('REMOTE_ADDR', '0.0.0.0'), 0), None)
    out = conn.out.getvalue()
    head, _, payload = out.partition(b'\r\n\r\n')
    lines = head.decode('latin-1').split('\r\n')
    status = lines[0].split(' ', 1)[1] if ' ' in lines[0] else '500 Internal Server Error'
    hdrs = [tuple(l.split(': ', 1)) for l in lines[1:] if ': ' in l and l.split(': ', 1)[0].lower() not in ('connection', 'transfer-encoding')]
    start_response(status, hdrs)
    return [payload]
