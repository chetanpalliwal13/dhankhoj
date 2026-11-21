"""Web server: static site + JSON API, using only the Python standard library.

    python3 server.py            # http://127.0.0.1:8080
"""
import base64
import hmac
import http.cookies
import json
import logging
import mimetypes
import os
import re
import secrets
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ingest
import notify
from config import Settings, HERE
from db import DB
from notify import Notifier
from auth import Auth
from billing import Billing
from claims import Claims
from service import ApiError, Service

log = logging.getLogger('dhankhoj')

WEB = os.path.join(HERE, 'web')
MAX_JSON = 64 * 1024
MAX_UPLOAD = 300 * 1024 * 1024
CSP = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
# Razorpay Checkout needs its script, an iframe and a few calls - allowed on the upgrade page only, and only when Razorpay is the configured gateway
CSP_RAZORPAY = ("default-src 'self'; img-src 'self' data: https://*.razorpay.com; style-src 'self' 'unsafe-inline'; script-src 'self' https://checkout.razorpay.com; "
                "connect-src 'self' https://api.razorpay.com https://lumberjack.razorpay.com https://checkout.razorpay.com; frame-src https://api.razorpay.com https://checkout.razorpay.com; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
MAX_WEBHOOK = 256 * 1024


class RateLimiter:
    def __init__(self):
        self.hits, self.lock = {}, threading.Lock()

    def allow(self, key, limit, window):
        now = time.time()
        with self.lock:
            q = [t for t in self.hits.get(key, []) if now - t < window]
            if len(q) >= limit:
                self.hits[key] = q
                return False
            q.append(now)
            self.hits[key] = q
            if len(self.hits) > 20000:  # keep memory bounded
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < window}
            return True


def make_handler(svc, st, rl):
    cl = Claims(svc)
    au = Auth(svc)
    bl = Billing(svc)
    COOKIE = '__Host-dk' if st.secure_cookies else 'dk_session'

    class H(BaseHTTPRequestHandler):
        server_version = 'DhanKhoj'
        protocol_version = 'HTTP/1.1'

        # ---------------------------------------------------------- helpers
        def log_message(self, fmt, *a):  # no query strings (they can carry tokens) and no bodies in logs
            path = self.path.split('?')[0]
            sys.stderr.write('%s %s %s\n' % (self.command, path, a[1] if len(a) > 1 else ''))

        def ip(self):
            if st.trust_proxy:
                xf = self.headers.get('X-Forwarded-For', '')
                if xf:
                    return xf.split(',')[0].strip()
            return self.client_address[0]

        def _headers(self, code, ctype, length, extra=None, csp=CSP):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(length))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', csp)
            self.send_header('X-Frame-Options', 'DENY')
            if st.secure_cookies:
                self.send_header('Strict-Transport-Security', 'max-age=31536000')
            for k, v in (extra.items() if isinstance(extra, dict) else (extra or [])):
                self.send_header(k, v)
            self.end_headers()

        def json(self, obj, code=200, close=False, cookies=()):
            b = json.dumps(obj, separators=(',', ':')).encode()
            extra = [('Cache-Control', 'no-store')] + [('Set-Cookie', c) for c in cookies]
            if close:
                extra.append(('Connection', 'close'))
                self.close_connection = True
            self._headers(code, 'application/json; charset=utf-8', len(b), extra)
            self.wfile.write(b)

        def fail(self, msg, code=400, **extra):
            # an unread request body would corrupt the next request on a kept-alive connection
            self.json({'ok': False, 'error': msg, **extra}, code, close=(self.command == 'POST'))

        # ---------------------------------------------------------- session cookie / current user
        def session_token(self):
            raw = self.headers.get('Cookie', '')
            if not raw:
                return ''
            try:
                c = http.cookies.SimpleCookie(raw)
            except http.cookies.CookieError:
                return ''
            return c[COOKIE].value if COOKIE in c else ''

        def set_cookie(self, token, max_age):
            parts = ['%s=%s' % (COOKIE, token), 'Path=/', 'HttpOnly', 'SameSite=Lax', 'Max-Age=%d' % max_age]
            if st.secure_cookies:
                parts.append('Secure')
            return '; '.join(parts)

        def user(self):
            u = au.user_for(self.session_token())
            if not u:
                raise ApiError('Please sign in to continue.', 401, need='login')
            return u

        def vuser(self):
            u = self.user()
            if not u['email_verified_at']:
                raise ApiError('Please confirm your email address first - we sent you a link.', 403, need='verify_email')
            return u

        def same_origin(self):
            # Cookies are SameSite=Lax and every POST must be application/json (which browsers will not send cross-site without a CORS preflight).
            # This extra check rejects a browser POST whose Origin is not this site.
            o = self.headers.get('Origin')
            if o and urllib.parse.urlsplit(o).netloc != (self.headers.get('Host') or ''):
                raise ApiError('Request blocked.', 403)

        def body_json(self):
            if 'application/json' not in (self.headers.get('Content-Type') or ''):
                raise ApiError('Content-Type must be application/json.', 415)
            n = int(self.headers.get('Content-Length') or 0)
            if n > MAX_JSON:
                raise ApiError('Request too large.', 413)
            try:
                d = json.loads(self.rfile.read(n) or b'{}')
            except ValueError:
                raise ApiError('Invalid JSON.')
            if not isinstance(d, dict):
                raise ApiError('Invalid request.')
            return d

        def admin(self):
            tok = self.headers.get('X-Admin-Token', '')
            if not st.admin_token or not hmac.compare_digest(tok.encode(), st.admin_token.encode()):
                time.sleep(0.4)
                raise ApiError('Admin access denied.', 403)

        def limit(self, key, n, window, msg='Too many requests. Please try again later.'):
            if not rl.allow(key, n, window):
                raise ApiError(msg, 429)

        # ---------------------------------------------------------- dispatch
        # ---------------------------------------------------------- Sign in with Google (OAuth 2.0 authorisation-code flow, server side)
        def redirect(self, loc, cookies=()):
            self._headers(302, 'text/plain; charset=utf-8', 0, [('Location', loc), ('Cache-Control', 'no-store')] + [('Set-Cookie', c) for c in cookies])

        def _gcookie(self, val, max_age):
            parts = ['dk_oauth=%s' % val, 'Path=/auth/google', 'HttpOnly', 'SameSite=Lax', 'Max-Age=%d' % max_age]
            if st.secure_cookies:
                parts.append('Secure')
            return '; '.join(parts)

        def google_start(self, q):
            if not (st.google_client_id and st.google_client_secret):
                return self.redirect('/signin.html?gerr=off')
            self.limit('gs:' + self.ip(), 40, 600)
            nxt = (q.get('next') or [''])[0]
            nxt = nxt if re.fullmatch(r'/[A-Za-z0-9_\-./?=&%]*', nxt) and not nxt.startswith('//') else '/dashboard.html'
            state = secrets.token_urlsafe(24)
            val = base64.urlsafe_b64encode(json.dumps({'s': state, 'n': nxt}).encode()).decode().rstrip('=')
            url = st.google_auth_url + '?' + urllib.parse.urlencode({'client_id': st.google_client_id, 'redirect_uri': st.base_url + '/auth/google/callback', 'response_type': 'code',
                                                                      'scope': 'openid email profile', 'state': state, 'prompt': 'select_account'})
            return self.redirect(url, [self._gcookie(val, 600)])

        def google_callback(self, q):
            self.limit('gc:' + self.ip(), 40, 600)
            clear = [self._gcookie('', 0)]
            try:
                raw = http.cookies.SimpleCookie(self.headers.get('Cookie', '')).get('dk_oauth')
                c = json.loads(base64.urlsafe_b64decode(raw.value + '=' * (-len(raw.value) % 4))) if raw else {}
            except Exception:
                c = {}
            state, code = (q.get('state') or [''])[0], (q.get('code') or [''])[0]
            if (q.get('error') or [''])[0]:
                return self.redirect('/signin.html?gerr=cancelled', clear)
            if not (c.get('s') and state and hmac.compare_digest(c['s'], state) and code):
                return self.redirect('/signin.html?gerr=state', clear)
            try:
                _, body = notify._http(st.google_token_url, form={'code': code, 'client_id': st.google_client_id, 'client_secret': st.google_client_secret,
                                                                   'redirect_uri': st.base_url + '/auth/google/callback', 'grant_type': 'authorization_code'})
                access = json.loads(body).get('access_token')
                req = urllib.request.Request(st.google_userinfo_url, headers={'Authorization': 'Bearer ' + str(access)})
                with urllib.request.urlopen(req, timeout=15) as r:
                    info = json.loads(r.read().decode('utf-8', 'replace'))
            except Exception as e:
                log.warning('google sign-in failed: %s', e)
                return self.redirect('/signin.html?gerr=failed', clear)
            try:
                tok, usr, created = au.google_login(info, self.ip())
            except ApiError as e:
                return self.redirect('/signin.html?gerr=' + ('unverified' if e.code == 403 else 'failed'), clear)
            return self.redirect(c.get('n') or '/dashboard.html', clear + [self.set_cookie(tok, st.session_days * 86400)])

        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(u.query)
            try:
                if u.path == '/auth/google/start':
                    return self.google_start(q)
                if u.path == '/auth/google/callback':
                    return self.google_callback(q)
                if u.path == '/api/auth/options':
                    return self.json({'ok': True, 'google': bool(st.google_client_id and st.google_client_secret)})
                if u.path == '/api/stats':
                    return self.json({'ok': True, **svc.public_stats()})
                if u.path == '/api/form-options':
                    import auth as A
                    return self.json({'ok': True, 'states': A.STATES, 'langs': A.LANGS})
                if u.path == '/api/plan':
                    return self.json({'ok': True, **bl.plan_info(au.user_for(self.session_token()))})
                if u.path == '/api/claim-info':
                    return self.json({'ok': True, 'fee_text': st.claim_fee_text, 'experts': cl.public_panel()})
                if u.path == '/api/session':
                    usr = au.user_for(self.session_token())
                    return self.json({'ok': True, 'user': au.session_info(usr) if usr else None})
                if u.path == '/api/dashboard':
                    self.limit('me:' + self.ip(), 60, 60)
                    usr = self.vuser()
                    d = svc.me(usr)
                    d['claims'] = cl.mine(usr['id'])
                    return self.json({'ok': True, **d})
                if u.path == '/api/account/profile':
                    return self.json({'ok': True, **au.profile(self.user())})
                if u.path == '/api/account/payments':
                    return self.json({'ok': True, 'payments': bl.history(self.user())})
                if u.path == '/api/pay/receipt':
                    return self.json({'ok': True, **bl.receipt(self.user(), int((q.get('id') or ['0'])[0]))})
                if u.path == '/api/admin/claims':
                    self.admin()
                    return self.json({'ok': True, 'claims': cl.admin_list(), 'experts': cl.admin_experts()})
                if u.path == '/api/admin/payments':
                    self.admin()
                    return self.json({'ok': True, 'payments': bl.admin_list()})
                if u.path == '/api/admin/stats':
                    self.admin()
                    return self.json({'ok': True, **svc.admin_stats()})
                if u.path == '/api/admin/companies':
                    self.admin()
                    term = (q.get('q') or [''])[0]
                    rows = svc.db.q('SELECT name, symbol FROM companies WHERE name LIKE ? ORDER BY name LIMIT 20', ('%' + term + '%',))
                    return self.json({'ok': True, 'companies': [dict(r) for r in rows]})
                if u.path.startswith('/api/'):
                    return self.fail('Not found', 404)
                return self.static(u.path)
            except ApiError as e:
                return self.fail(e.msg, e.code, **e.extra)
            except ValueError:
                return self.fail('Invalid request.')
            except Exception as e:
                sys.stderr.write('ERROR %s %r\n' % (u.path, e))
                return self.fail('Something went wrong on our side.', 500)

        def do_POST(self):
            u = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(u.query)
            ip = self.ip()
            try:
                if u.path == '/api/webhook/razorpay':  # server-to-server: no cookies, authenticated by signature
                    self.limit('wh:' + ip, 300, 60)
                    n = int(self.headers.get('Content-Length') or 0)
                    if n <= 0 or n > MAX_WEBHOOK:
                        raise ApiError('Bad request.', 413)
                    return self.json({'ok': True, **bl.webhook_razorpay(self.rfile.read(n), self.headers.get('X-Razorpay-Signature', ''))})
                self.same_origin()
                # ---- public: accounts
                if u.path == '/api/check':
                    self.limit('check:' + ip, 20, 60)
                    d = self.body_json()
                    return self.json({'ok': True, **svc.check(d.get('name', ''), d.get('pincode', ''), d.get('folio', ''))})
                if u.path == '/api/auth/signup':
                    self.limit('su:' + ip, 10, 3600)
                    d = self.body_json()
                    self.limit('suc:' + str(d.get('email', '')).lower(), 5, 3600)
                    return self.json({'ok': True, **au.signup(d, ip)})
                if u.path == '/api/auth/login':
                    self.limit('li:' + ip, 30, 600, 'Too many sign-in attempts. Please wait a few minutes.')
                    d = self.body_json()
                    self.limit('lic:' + str(d.get('email', '')).lower(), 10, 900, 'Too many sign-in attempts. Please wait a few minutes.')
                    tok, usr = au.login(d.get('email', ''), d.get('password', ''), ip)
                    return self.json({'ok': True, 'user': au.session_info(usr)}, cookies=[self.set_cookie(tok, st.session_days * 86400)])
                if u.path == '/api/auth/logout':
                    self.body_json()
                    au.logout(self.session_token())
                    return self.json({'ok': True}, cookies=[self.set_cookie('', 0)])
                if u.path == '/api/auth/verify-email':
                    self.limit('ve:' + ip, 30, 3600)
                    return self.json({'ok': True, **au.verify_email(self.body_json().get('token', ''))})
                if u.path == '/api/auth/resend-verification':
                    self.limit('rv:' + ip, 10, 3600)
                    d = self.body_json()
                    usr = au.user_for(self.session_token())
                    email = d.get('email') or (usr['email'] if usr else '')
                    self.limit('rvc:' + str(email).lower(), 3, 3600, 'Please wait a little before asking for another email.')
                    return self.json({'ok': True, **au.resend_verification(email)})
                if u.path == '/api/auth/forgot':
                    self.limit('fp:' + ip, 10, 3600)
                    d = self.body_json()
                    self.limit('fpc:' + str(d.get('email', '')).lower(), 3, 3600, 'Please wait a little before asking for another email.')
                    return self.json({'ok': True, **au.forgot(d.get('email', ''))})
                if u.path == '/api/auth/reset-check':
                    self.limit('rc:' + ip, 30, 3600)
                    return self.json({'ok': True, 'valid': au.check_reset_token(self.body_json().get('token', ''))})
                if u.path == '/api/auth/reset':
                    self.limit('rp:' + ip, 20, 3600)
                    d = self.body_json()
                    return self.json({'ok': True, **au.reset(d.get('token', ''), d.get('password', ''))})
                if u.path == '/api/unsub/info':
                    self.limit('ui:' + ip, 60, 3600)
                    return self.json({'ok': True, **au.unsub_info(self.body_json().get('t', ''))})
                if u.path == '/api/unsub/set':
                    self.limit('us:' + ip, 30, 3600)
                    d = self.body_json()
                    return self.json({'ok': True, **au.unsub_set(d.get('t', ''), d.get('what', ''), ip)})
                # ---- signed-in account
                if u.path == '/api/account/profile':
                    self.limit('ap:' + ip, 30, 3600)
                    usr = self.user()
                    return self.json({'ok': True, **au.update_profile(usr, self.body_json(), ip)})
                if u.path == '/api/account/password':
                    self.limit('pw:' + ip, 10, 3600)
                    usr = self.user()
                    d = self.body_json()
                    return self.json({'ok': True, **au.change_password(usr, d.get('current', ''), d.get('new', ''), self.session_token())})
                if u.path == '/api/account/delete':
                    self.limit('del:' + ip, 5, 3600)
                    usr = self.user()
                    r = au.delete_account(usr, self.body_json().get('password', ''), ip)
                    return self.json({'ok': True, **r}, cookies=[self.set_cookie('', 0)])
                if u.path == '/api/account/phone/send-otp':
                    self.limit('po:' + ip, 10, 3600)
                    usr = self.user()
                    self.limit('poc:%d' % usr['id'], 5, 3600)
                    self.body_json()
                    return self.json({'ok': True, **au.phone_send_otp(usr)})
                if u.path == '/api/account/phone/verify':
                    self.limit('pv:' + ip, 20, 3600)
                    usr = self.user()
                    return self.json({'ok': True, **au.phone_verify(usr, self.body_json().get('otp', ''))})
                if u.path == '/api/account/channels':
                    self.limit('ch:' + ip, 30, 3600)
                    usr = self.user()
                    return self.json({'ok': True, 'channels': au.set_channels(usr, self.body_json().get('channels') or {}, ip)})
                # ---- dashboard actions (email must be confirmed)
                if u.path == '/api/me/claim':
                    self.limit('cl:' + ip, 15, 3600)
                    usr = self.vuser()
                    return self.json(cl.create(usr, self.body_json()))
                if u.path == '/api/me/claim/respond':
                    self.limit('clr:' + ip, 30, 3600)
                    usr = self.vuser()
                    d = self.body_json()
                    return self.json(cl.respond(usr, int(d.get('id', 0)), bool(d.get('accept'))))
                # ---- payments
                if u.path == '/api/pay/order':
                    self.limit('po2:' + ip, 20, 3600)
                    usr = self.vuser()
                    d = self.body_json()
                    return self.json({'ok': True, **bl.create_order(usr, d.get('tier'), d.get('period'))})
                if u.path == '/api/pay/confirm':
                    self.limit('pc:' + ip, 30, 3600)
                    usr = self.vuser()
                    return self.json({'ok': True, **bl.confirm_checkout(usr, self.body_json())})
                if u.path == '/api/pay/mock-confirm':
                    usr = self.vuser()
                    return self.json({'ok': True, **bl.mock_confirm(usr, int(self.body_json().get('payment_id', 0)))})
                if u.path == '/api/pay/upi/start':
                    self.limit('us2:' + ip, 20, 3600)
                    usr = self.vuser()
                    d = self.body_json()
                    return self.json({'ok': True, **bl.upi_start(usr, d.get('tier'), d.get('period'))})
                if u.path == '/api/pay/upi/submit':
                    self.limit('uu:' + ip, 20, 3600)
                    usr = self.vuser()
                    d = self.body_json()
                    return self.json({'ok': True, **bl.upi_submit(usr, int(d.get('payment_id', 0)), d.get('utr', ''))})
                # ---- experts
                if u.path == '/api/expert/register':
                    self.limit('ex:' + ip, 5, 3600)
                    return self.json(cl.register_expert(self.body_json()))
                # ---- admin
                if u.path == '/api/admin/claim/update':
                    self.admin()
                    d = self.body_json()
                    return self.json(cl.admin_update(int(d.get('id', 0)), d))
                if u.path == '/api/admin/expert/update':
                    self.admin()
                    d = self.body_json()
                    return self.json(cl.admin_set_expert(int(d.get('id', 0)), d.get('status', ''), d.get('note', '')))
                if u.path == '/api/admin/payment/review':
                    self.admin()
                    d = self.body_json()
                    return self.json({'ok': True, **bl.admin_review(int(d.get('id', 0)), bool(d.get('approve')), d.get('note', ''))})
                if u.path == '/api/admin/grant':
                    self.admin()
                    d = self.body_json()
                    return self.json({'ok': True, **bl.admin_grant(d.get('email', ''), d.get('tier', ''), d.get('days', 0), d.get('note', ''))})
                if u.path == '/api/admin/ingest':
                    self.admin()
                    return self.admin_ingest(q)
                if u.path == '/api/admin/tick':
                    self.admin()
                    return self.json({'ok': True, **svc.tick()})
                return self.fail('Not found', 404)
            except ApiError as e:
                return self.fail(e.msg, e.code, **e.extra)
            except ValueError:
                return self.fail('Invalid request.')
            except Exception as e:
                sys.stderr.write('ERROR %s %r\n' % (u.path, e))
                return self.fail('Something went wrong on our side.', 500)

        def admin_ingest(self, q):
            n = int(self.headers.get('Content-Length') or 0)
            if n <= 0 or n > MAX_UPLOAD:
                raise ApiError('Upload is empty or larger than %d MB.' % (MAX_UPLOAD // 2 ** 20), 413)
            company = (q.get('company') or [''])[0].strip()
            if not company:
                raise ApiError('company is required')
            ext = os.path.splitext((q.get('filename') or ['list.txt'])[0])[1].lower()
            if ext not in ('.pdf', '.csv', '.txt', '.xlsx', '.xlsm'):
                raise ApiError('Supported files: PDF, CSV, TXT, XLSX')
            fd, path = tempfile.mkstemp(suffix=ext, prefix='upl_')
            try:
                with os.fdopen(fd, 'wb') as f:
                    left = n
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            raise ApiError('Upload interrupted.')
                        f.write(chunk)
                        left -= len(chunk)
                res = ingest.ingest_file(svc.db, company, path, fy=(q.get('fy') or [None])[0] or None, dtype=(q.get('type') or [None])[0] or None,
                                         source_url=(q.get('url') or [''])[0], declared_on=(q.get('declared') or [None])[0] or None)
            except (RuntimeError, ValueError) as e:
                raise ApiError(str(e))
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            if res.get('status') == 'ok':
                threading.Thread(target=svc.tick, daemon=True).start()
            return self.json({'ok': res.get('status') != 'error', **res})

        # ---------------------------------------------------------- static files
        def static(self, path):
            path = urllib.parse.unquote(path)
            if path in ('', '/'):
                path = '/index.html'
            full = os.path.normpath(os.path.join(WEB, path.lstrip('/')))
            if not full.startswith(WEB + os.sep) or not os.path.isfile(full):
                return self.fail('Not found', 404)
            ext = os.path.splitext(full)[1].lower()
            if ext not in ('.html', '.css', '.js', '.svg', '.png', '.ico', '.woff', '.txt', '.webmanifest'):
                return self.fail('Not found', 404)
            with open(full, 'rb') as fh:
                data = fh.read()
            ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
            if ext in ('.html', '.js', '.css', '.svg'):
                ctype += '; charset=utf-8'
            csp = CSP_RAZORPAY if (os.path.basename(full) == 'upgrade.html' and bl.provider() == 'razorpay') else CSP
            self._headers(200, ctype, len(data), {'Cache-Control': 'no-cache' if ext in ('.html', '.js', '.css') else 'public, max-age=3600'}, csp=csp)
            if self.command != 'HEAD':
                self.wfile.write(data)

        do_HEAD = do_GET

    return H


def start_worker(svc, interval):
    def loop():
        while True:
            try:
                svc.tick()
            except Exception as e:
                sys.stderr.write('worker error: %r\n' % (e,))
            time.sleep(interval)
    t = threading.Thread(target=loop, daemon=True, name='worker')
    t.start()
    return t


def build(st=None):
    st = st or Settings()
    db = DB(st.db_path)
    svc = Service(db, st, Notifier(st))
    return st, db, svc


def main():
    st, db, svc = build()
    if not st.admin_token:
        print('NOTE: ADMIN_TOKEN is not set, the admin page is disabled.', file=sys.stderr)
    if st.salt == 'change-me' and not st.dev_mode:
        print('WARNING: set APP_SALT to a long random value in .env before going live.', file=sys.stderr)
    if not st.data_key and not st.dev_mode:
        print('WARNING: set DATA_KEY in .env (encrypts PANs). Without it the key is derived from APP_SALT.', file=sys.stderr)
    if st.pay_provider == 'razorpay' and not st.razorpay_webhook_secret:
        print('NOTE: RAZORPAY_WEBHOOK_SECRET is not set; payments will only confirm when the customer\'s browser returns.', file=sys.stderr)
    if st.pay_provider == 'mock' and not st.dev_mode:
        print('NOTE: PAY_PROVIDER=mock only works with DEV_MODE=1; online payment is switched off.', file=sys.stderr)
    if st.dev_mode:
        print('DEV_MODE is on: OTP codes are returned in API responses. Never use this in production.', file=sys.stderr)
    if st.worker_interval > 0:
        start_worker(svc, st.worker_interval)
    srv = ThreadingHTTPServer((st.host, st.port), make_handler(svc, st, RateLimiter()))
    print('%s running on http://%s:%d' % (st.brand, st.host, st.port), file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
