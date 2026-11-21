"""Accounts: registration, sign-in sessions, email-link verification, password reset, profile, mobile OTP,
alert subscriptions with a consent log, and account deletion.

A user account is a row in `subscribers` (the table the matching engine already uses), so `sub_id` everywhere means "user id".
Secrets: passwords use scrypt; session / email / reset tokens are random and only their SHA-256 is stored; the PAN is stored
encrypted (Vault) plus a keyed hash used only to stop duplicate accounts.
"""
import base64
import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time

import matcher as M
from service import (ApiError, clean_folios, clean_name, clean_pin, mask_email, mask_phone, norm_email, norm_phone, now_iso)

PAN_RE = re.compile(r'^[A-Z]{3}[ABCFGHLJPKT][A-Z][0-9]{4}[A-Z]$')  # 4th letter = holder type (P person, C company, H HUF ...)
STATES = ('Andaman and Nicobar Islands', 'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chandigarh', 'Chhattisgarh',
          'Dadra and Nagar Haveli and Daman and Diu', 'Delhi', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jammu and Kashmir', 'Jharkhand',
          'Karnataka', 'Kerala', 'Ladakh', 'Lakshadweep', 'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha',
          'Puducherry', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal')
LANGS = ('English', 'Hindi', 'Marathi', 'Gujarati', 'Bengali', 'Tamil', 'Telugu', 'Kannada', 'Malayalam', 'Punjabi', 'Odia', 'Other')
COMMON_PW = {'password', 'password1', 'password123', '12345678', '123456789', '1234567890', 'qwertyuiop', 'qwerty123', 'iloveyou1', 'abcd1234',
             'welcome123', 'admin123', 'letmein123', 'india1234', 'dhankhoj', 'dhankhoj123'}


# ----------------------------------------------------------------------------- crypto helpers
class Vault:
    """Encrypt-then-MAC with HMAC-SHA256 only (no third-party packages): a keyed-HMAC counter-mode keystream plus an HMAC tag.
    Used for the PAN. Keep DATA_KEY secret and never change it, or stored PANs cannot be read back."""

    def __init__(self, key):
        m = hashlib.sha256(b'dhankhoj-vault|' + key.encode()).digest()
        self.k_enc = hmac.new(m, b'enc', hashlib.sha256).digest()
        self.k_mac = hmac.new(m, b'mac', hashlib.sha256).digest()
        self.k_idx = hmac.new(m, b'idx', hashlib.sha256).digest()

    def _stream(self, nonce, n):
        out, i = b'', 0
        while len(out) < n:
            out += hmac.new(self.k_enc, nonce + i.to_bytes(8, 'big'), hashlib.sha256).digest()
            i += 1
        return out[:n]

    def seal(self, text):
        raw = text.encode()
        nonce = secrets.token_bytes(16)
        ct = bytes(a ^ b for a, b in zip(raw, self._stream(nonce, len(raw))))
        tag = hmac.new(self.k_mac, b'v1' + nonce + ct, hashlib.sha256).digest()
        return 'v1.' + base64.urlsafe_b64encode(nonce + ct + tag).decode()

    def open(self, blob):
        try:
            raw = base64.urlsafe_b64decode((blob or '').split('.', 1)[1].encode())
            nonce, ct, tag = raw[:16], raw[16:-32], raw[-32:]
            if not hmac.compare_digest(tag, hmac.new(self.k_mac, b'v1' + nonce + ct, hashlib.sha256).digest()):
                return None
            return bytes(a ^ b for a, b in zip(ct, self._stream(nonce, len(ct)))).decode()
        except Exception:
            return None

    def index(self, text):
        return hmac.new(self.k_idx, text.encode(), hashlib.sha256).hexdigest()


def hash_password(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return 'scrypt$14$8$1$%s$%s' % (base64.b64encode(salt).decode(), base64.b64encode(h).decode())


def check_password(pw, stored):
    try:
        _, ln, r, p, salt, h = stored.split('$')
        calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=2 ** int(ln), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


_DUMMY = None


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


# ----------------------------------------------------------------------------- validation
def clean_pan(s):
    s = re.sub(r'\s+', '', str(s or '')).upper()
    if len(s) != 10:
        raise ApiError('A PAN has exactly 10 characters; you entered %d. Example: ABCPE1234F.' % len(s))
    if not PAN_RE.match(s):
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', s):
            raise ApiError('A PAN is 5 letters, 4 digits, then 1 letter. Example: ABCPE1234F.')
        raise ApiError('The 4th letter of a PAN shows the holder type and must be one of A, B, C, F, G, H, J, K, L, P or T (P for an individual). Please check "%s" against your PAN card.' % s[3])
    return s


def mask_pan(last4):
    return 'XXXXXX' + (last4 or '????')


def clean_password(pw, *avoid):
    pw = str(pw or '')
    if len(pw) < 8:
        raise ApiError('Password must be at least 8 characters.')
    if len(pw) > 128:
        raise ApiError('Password is too long (max 128 characters).')
    if pw.isdigit() or pw.lower() in COMMON_PW:
        raise ApiError('That password is too easy to guess. Add letters and numbers or use a longer phrase.')
    low = pw.lower()
    for a in avoid:
        if a and len(a) >= 4 and a.lower() in low:
            raise ApiError('Your password should not contain your name, email, PAN or mobile number.')
    return pw


def _word(s, field, req=True, n=40):
    s = re.sub(r"[^A-Za-z .'\-]", '', re.sub(r'\s+', ' ', str(s or ''))).strip()
    if not s:
        if req:
            raise ApiError('%s is required.' % field)
        return ''
    if len(s) > n or not re.search(r'[A-Za-z]', s):
        raise ApiError('%s looks wrong.' % field)
    return s


def _text(s, n, field='', req=False):
    s = re.sub(r'[\x00-\x1f\x7f]+', ' ', str(s or ''))
    s = re.sub(r'\s+', ' ', s).strip()
    if req and not s:
        raise ApiError('%s is required.' % field)
    return s[:n]


def clean_dob(s):
    s = str(s or '').strip()
    if not s:
        return None
    try:
        d = dt.date.fromisoformat(s)
    except ValueError:
        raise ApiError('Date of birth must look like 1975-08-21.')
    age = (dt.date.today() - d).days / 365.25
    if age < 18:
        raise ApiError('You must be 18 or older to register.')
    if age > 110:
        raise ApiError('Date of birth looks wrong.')
    return d.isoformat()


def _opt_phone(s):
    return norm_phone(s) if str(s or '').strip() else ''


def _opt_choice(s, choices, field):
    s = str(s or '').strip()
    if s and s not in choices:
        raise ApiError('%s is not a valid choice.' % field)
    return s


# ----------------------------------------------------------------------------- service
class Auth:
    def __init__(self, svc):
        self.svc, self.db, self.st, self.n = svc, svc.db, svc.st, svc.n
        self.vault = svc.vault

    # -------------------------------------------------------------- helpers
    def _by_email(self, email):
        return self.db.one('SELECT * FROM subscribers WHERE email=? AND password_hash IS NOT NULL', (email,))

    def _get(self, uid):
        return self.db.one('SELECT * FROM subscribers WHERE id=?', (uid,))

    def _consent(self, uid, subject, action, source, ip):
        self.db.x('INSERT INTO consents(user_id,subject,action,source,ip,at) VALUES(?,?,?,?,?,?)', (uid, subject, action, source, ip or '', now_iso()))

    def _issue(self, uid, kind, ttl):
        """New single-use token; any earlier unused token of the same kind stops working."""
        raw = secrets.token_urlsafe(32)
        t = time.time()
        self.db.conn.execute('UPDATE auth_tokens SET used_at=? WHERE user_id=? AND kind=? AND used_at IS NULL', (t, uid, kind))
        self.db.conn.execute('INSERT INTO auth_tokens(user_id,kind,token_hash,exp,created_at) VALUES(?,?,?,?,?)', (uid, kind, _sha(raw), t + ttl, t))
        self.db.conn.commit()
        return raw

    def _recent_token(self, uid, kind, within=60):
        return self.db.one('SELECT 1 FROM auth_tokens WHERE user_id=? AND kind=? AND created_at>?', (uid, kind, time.time() - within))

    def _take(self, raw, kind):
        """Validate and use up a token. Returns user id, or raises."""
        r = self.db.one('SELECT * FROM auth_tokens WHERE token_hash=? AND kind=?', (_sha(str(raw or '')), kind))
        if not r or r['used_at'] is not None or r['exp'] < time.time():
            raise ApiError('This link is invalid, already used or has expired. Please request a new one.', 410)
        cur = self.db.x('UPDATE auth_tokens SET used_at=? WHERE id=? AND used_at IS NULL', (time.time(), r['id']))
        if cur.rowcount != 1:
            raise ApiError('This link is invalid, already used or has expired. Please request a new one.', 410)
        return r['user_id']

    def _mail(self, u, subject, body):
        ok, err = self.n.send('email', u['email'], body, subject=subject, kind='account')
        return ok

    def _first(self, u):
        return (u['first_name'] or u['name'].split()[0]).title()

    # -------------------------------------------------------------- registration
    def signup(self, p, ip=''):
        """Simple registration: name, mobile, email, password. PAN, DP-Client IDs and the optional record-keeping details are added later in the profile."""
        if p.get('consent') is not True:
            raise ApiError('Please confirm you are 18 or older and accept the Terms and Privacy Notice.')
        first, last = _word(p.get('first_name'), 'First name'), _word(p.get('last_name'), 'Last name')
        middle = _word(p.get('middle_name'), 'Middle name', req=False)
        name = clean_name(' '.join(x for x in (first, middle, last) if x))
        email, phone = norm_email(p.get('email')), norm_phone(p.get('mobile'))
        pw = clean_password(p.get('password'), first, last, email.split('@')[0], phone[-10:])
        ch = p.get('channels') or {}
        ch_email, ch_sms, ch_wa = int(bool(ch.get('email', True))), 0, 0  # SMS / WhatsApp are switched on later, after mobile verification and only on plans that include them
        generic = ApiError('An account already exists with some of these details. Try signing in, or use "Forgot password".', 409)
        legacy = self.db.q('SELECT id FROM subscribers WHERE email=? AND password_hash IS NULL ORDER BY id', (email,))
        taken = self.db.one('SELECT 1 FROM subscribers WHERE password_hash IS NOT NULL AND (email=? OR phone=?)', (email, phone))
        if taken:
            raise generic
        cols = 'first_name,middle_name,last_name,name,aliases,email,phone,pincode,folios,ch_email,ch_sms,ch_wa,password_hash,pan_hash,pan_enc,pan_last4,terms_at,consent_at'
        row = (first, middle, last, name, '[]', email, phone, None, '[]', ch_email, ch_sms, ch_wa, hash_password(pw), None, None, None, now_iso(), now_iso())
        try:
            if legacy:  # an old anonymous subscription on this email: adopt it, drop the rest. The email link below proves ownership.
                uid = legacy[0]['id']
                for extra_row in legacy[1:]:
                    self.svc.delete_user_data(extra_row['id'])
                self.db.x("UPDATE subscribers SET %s, status='pending', email_verified_at=NULL, phone_verified_at=NULL, otp_phone=NULL, token=?, created_at=? WHERE id=?"
                          % ','.join(c + '=?' for c in cols.split(',')), row + (secrets.token_urlsafe(32), now_iso(), uid))
                self.db.x('DELETE FROM matches WHERE sub_id=?', (uid,))
            else:
                cur = self.db.x('INSERT INTO subscribers(%s,status,token,created_at) VALUES(%s,?,?,?)' % (cols, ','.join('?' * 18)), row + ('pending', secrets.token_urlsafe(32), now_iso()))
                uid = cur.lastrowid
        except sqlite3.IntegrityError:
            raise generic
        self._consent(uid, 'terms', 'grant', 'signup', ip)
        if ch_email:
            self._consent(uid, 'email', 'grant', 'signup', ip)
        out = {'email': mask_email(email)}
        if self.st.skip_email_verify:  # local demo: no mail server needed, the account is usable straight away
            self.db.x("UPDATE subscribers SET status='active', email_verified_at=?, verified_at=? WHERE id=?", (now_iso(), now_iso(), uid))
            out['verified'] = True
            return out
        out.update(self._send_verification(self._get(uid)))
        return out

    def _optional(self, p):
        """Optional record-keeping fields; every one may be blank."""
        return {
            'dob': clean_dob(p.get('dob')),
            'father_name': _word(p.get('father_name'), "Father's / spouse's name", req=False, n=80),
            'address': _text(p.get('address'), 250, 'Address'),
            'city': _text(p.get('city'), 60),
            'state': _opt_choice(p.get('state'), STATES, 'State'),
            'pincode': clean_pin(p.get('pincode')),
            'alt_phone': _opt_phone(p.get('alt_mobile')),
            'lang': _opt_choice(p.get('lang'), LANGS, 'Language'),
        }

    def _send_verification(self, u):
        raw = self._issue(u['id'], 'verify_email', self.st.verify_ttl)
        link = '%s/verify-email.html?token=%s' % (self.st.base_url, raw)
        hours = self.st.verify_ttl // 3600
        self._mail(u, 'Confirm your email for %s' % self.st.brand,
                   'Hello %s,\n\nThanks for registering with %s. Please confirm your email address to activate your account:\n\n%s\n\n'
                   'The link works once and expires in %d hours. If you did not register, ignore this email - nothing will happen.\n' % (self._first(u), self.st.brand, link, hours))
        return {'dev_link': link} if self.st.dev_mode else {}

    def verify_email(self, raw):
        r = self.db.one('SELECT * FROM auth_tokens WHERE token_hash=? AND kind=?', (_sha(str(raw or '')), 'verify_email'))
        if r and r['used_at'] is not None:  # clicking the same link twice (or a mail scanner opened it) is fine
            u = self._get(r['user_id'])
            if u and u['email_verified_at']:
                return {'already': True, 'email': mask_email(u['email'])}
        uid = self._take(raw, 'verify_email')
        u = self._get(uid)
        if not u:
            raise ApiError('This account no longer exists.', 404)
        self._activate(uid)
        return {'already': False, 'email': mask_email(u['email'])}

    def _activate(self, uid):
        self.db.x("UPDATE subscribers SET status='active', email_verified_at=COALESCE(email_verified_at,?), verified_at=COALESCE(verified_at,?) WHERE id=?", (now_iso(), now_iso(), uid))
        self.svc.match_subscriber(uid)
        self.svc.process_alerts(only_sub=uid)
        self.svc.dispatch_outbox()

    def resend_verification(self, email):
        u = self._by_email(norm_email(email))
        out = {}
        if u and not u['email_verified_at'] and not self._recent_token(u['id'], 'verify_email'):
            out = self._send_verification(u)
        return out  # the caller always shows the same message, so this cannot be used to find registered emails

    # -------------------------------------------------------------- sign-in / sessions
    def login(self, email, password, ip=''):
        global _DUMMY
        if _DUMMY is None:
            _DUMMY = hash_password('dummy-password-for-timing')
        fail = ApiError('Incorrect email or password.', 401)
        try:
            email = norm_email(email)
        except ApiError:
            raise fail
        u = self._by_email(email)
        if u and (u['locked_until'] or 0) > time.time():
            raise ApiError('Too many failed attempts. Please wait 15 minutes or reset your password.', 429)
        ok = check_password(str(password or ''), u['password_hash'] if u else _DUMMY)
        if not (u and ok):
            if u:
                fails = (u['login_fails'] or 0) + 1
                if fails >= 10:
                    self.db.x('UPDATE subscribers SET login_fails=0, locked_until=? WHERE id=?', (time.time() + 900, u['id']))
                else:
                    self.db.x('UPDATE subscribers SET login_fails=? WHERE id=?', (fails, u['id']))
            raise fail
        return self._start_session(u, ip), u

    def _start_session(self, u, ip=''):
        self.db.x('UPDATE subscribers SET login_fails=0, locked_until=0, last_login_at=? WHERE id=?', (now_iso(), u['id']))
        tok = secrets.token_urlsafe(32)
        t = time.time()
        self.db.x('INSERT INTO sessions(user_id,token_hash,created_at,expires_at,ip) VALUES(?,?,?,?,?)', (u['id'], _sha(tok), t, t + self.st.session_days * 86400, ip))
        return tok

    # -------------------------------------------------------------- Sign in with Google
    def google_login(self, info, ip=''):
        """info = the verified profile Google returned (sub, email, email_verified, given_name, family_name, name). Returns (session token, user, created)."""
        if info.get('email_verified') not in (True, 'true'):
            raise ApiError('Google has not verified this email address, so we cannot use it.', 403)
        email, sub = norm_email(info.get('email')), str(info.get('sub') or '')
        if not sub:
            raise ApiError('Google did not return an account id.', 502)
        u = self.db.one('SELECT * FROM subscribers WHERE google_sub=? AND password_hash IS NOT NULL', (sub,))
        created = False
        if not u:
            u = self._by_email(email)
            if u:  # an account with this email already exists: link Google to it
                sets = {'google_sub': sub}
                if not u['email_verified_at']:
                    # whoever registered this address by password never proved they own it, Google just did: cancel their password and sessions
                    sets.update(password_hash=hash_password(secrets.token_urlsafe(24)), email_verified_at=now_iso())
                    self.db.x('DELETE FROM sessions WHERE user_id=?', (u['id'],))
                self.db.x('UPDATE subscribers SET %s WHERE id=?' % ','.join(k + '=?' for k in sets), tuple(sets.values()) + (u['id'],))
                if 'email_verified_at' in sets:
                    self._activate(u['id'])
            else:
                u, created = self._google_new(info, email, sub, ip), True
            u = self._get(u['id'])
        return self._start_session(u, ip), u, created

    def _google_new(self, info, email, sub, ip):
        first = ''
        for cand in (info.get('given_name'), (info.get('name') or '').split(' ')[0], email.split('@')[0]):
            try:
                first = first or _word(cand, 'First name', req=False)
            except ApiError:
                pass
        first = first or 'Member'
        try:
            last = _word(info.get('family_name'), 'Last name', req=False)
        except ApiError:
            last = ''
        try:
            name = clean_name(' '.join(x for x in (first, last) if x))
        except ApiError:
            name = clean_name(first + ' (Google)') if len(first) < 3 else 'Google member'
        for old in self.db.q('SELECT id FROM subscribers WHERE email=? AND password_hash IS NULL', (email,)):  # old anonymous subscriptions: Google just proved the address is theirs
            self.svc.delete_user_data(old['id'])
        t = now_iso()
        cur = self.db.x("INSERT INTO subscribers(first_name,middle_name,last_name,name,aliases,email,phone,folios,ch_email,ch_sms,ch_wa,password_hash,terms_at,consent_at,google_sub,"
                        "status,email_verified_at,verified_at,token,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (first, '', last, name, '[]', email, '', '[]', 1, 0, 0, hash_password(secrets.token_urlsafe(24)), t, t, sub, 'active', t, t, secrets.token_urlsafe(32), t))
        uid = cur.lastrowid
        self._consent(uid, 'terms', 'grant', 'google', ip)
        self._consent(uid, 'email', 'grant', 'google', ip)
        self._activate(uid)
        return self._get(uid)

    def user_for(self, token):
        if not token:
            return None
        t = time.time()
        r = self.db.one('SELECT s.*, x.last_seen AS _seen, x.created_at AS _made FROM sessions x JOIN subscribers s ON s.id=x.user_id WHERE x.token_hash=? AND x.expires_at>?', (_sha(token), t))
        if not r:
            return None
        idle = self.st.session_idle_min
        seen = r['_seen'] or r['_made'] or t
        if idle > 0 and t - seen > (idle + 1) * 60:  # idle too long: end the session (the page also signs out after `idle` minutes)
            self.db.x('DELETE FROM sessions WHERE token_hash=?', (_sha(token),))
            return None
        if t - seen > 20:
            self.db.x('UPDATE sessions SET last_seen=? WHERE token_hash=?', (t, _sha(token)))
        return r

    def logout(self, token):
        if token:
            self.db.x('DELETE FROM sessions WHERE token_hash=?', (_sha(token),))

    def session_info(self, u):
        return {'first_name': self._first(u), 'name': u['name'], 'email': mask_email(u['email']), 'email_verified': bool(u['email_verified_at']),
                'phone_verified': bool(u['phone_verified_at']), 'plan': self.svc.plan_state(u), 'idle_min': self.st.session_idle_min}

    # -------------------------------------------------------------- forgot / reset / change password
    def forgot(self, email):
        try:
            email = norm_email(email)
        except ApiError:
            return {}
        u = self._by_email(email)
        out = {}
        if u and not self._recent_token(u['id'], 'reset'):
            raw = self._issue(u['id'], 'reset', self.st.reset_ttl)
            link = '%s/reset.html?token=%s' % (self.st.base_url, raw)
            self._mail(u, 'Reset your %s password' % self.st.brand,
                       'Hello %s,\n\nWe received a request to reset your %s password. Choose a new one here:\n\n%s\n\n'
                       'The link works once and expires in %d minutes. If you did not ask for this, ignore this email - your password stays the same.\n' % (self._first(u), self.st.brand, link, self.st.reset_ttl // 60))
            if self.st.dev_mode:
                out['dev_link'] = link
        return out

    def check_reset_token(self, raw):
        r = self.db.one('SELECT * FROM auth_tokens WHERE token_hash=? AND kind=?', (_sha(str(raw or '')), 'reset'))
        return bool(r and r['used_at'] is None and r['exp'] > time.time())

    def reset(self, raw, password):
        r = self.db.one('SELECT user_id FROM auth_tokens WHERE token_hash=? AND kind=?', (_sha(str(raw or '')), 'reset'))
        u = self._get(r['user_id']) if r else None
        if not u:
            raise ApiError('This link is invalid, already used or has expired. Please request a new one.', 410)
        pw = clean_password(password, u['first_name'], u['last_name'], u['email'].split('@')[0], u['phone'][-10:])  # validate before the token is used up
        uid = self._take(raw, 'reset')
        self.db.x('UPDATE subscribers SET password_hash=?, login_fails=0, locked_until=0 WHERE id=?', (hash_password(pw), uid))
        self.db.x('DELETE FROM sessions WHERE user_id=?', (uid,))
        if not u['email_verified_at']:  # a working reset link proves the mailbox is theirs
            self._activate(uid)
        self._mail(u, 'Your %s password was changed' % self.st.brand,
                   'Hello %s,\n\nYour %s password was just changed and you were signed out everywhere. If this was not you, reset it again now at %s/forgot.html and contact us.\n' % (self._first(u), self.st.brand, self.st.base_url))
        return {}

    def change_password(self, u, current, new, session_token):
        if not check_password(str(current or ''), u['password_hash']):
            raise ApiError('Your current password is not correct.', 403)
        pw = clean_password(new, u['first_name'], u['last_name'], u['email'].split('@')[0], u['phone'][-10:])
        self.db.x('UPDATE subscribers SET password_hash=? WHERE id=?', (hash_password(pw), u['id']))
        self.db.x('DELETE FROM sessions WHERE user_id=? AND token_hash!=?', (u['id'], _sha(session_token or '')))
        self._mail(u, 'Your %s password was changed' % self.st.brand, 'Hello %s,\n\nYour password was changed from your account page. If this was not you, reset it now at %s/forgot.html.\n' % (self._first(u), self.st.base_url))
        return {}

    # -------------------------------------------------------------- profile
    def profile(self, u):
        pan = self.vault.open(u['pan_enc']) if u['pan_enc'] else None
        return {'first_name': u['first_name'], 'middle_name': u['middle_name'] or '', 'last_name': u['last_name'], 'email': u['email'], 'mobile': u['phone'][3:],
                'pan_set': bool(u['pan_hash']), 'pan_masked': mask_pan(u['pan_last4']) if u['pan_hash'] else '', 'pan_ok': pan is not None, 'dob': u['dob'] or '', 'father_name': u['father_name'] or '', 'address': u['address'] or '',
                'city': u['city'] or '', 'state': u['state'] or '', 'pincode': u['pincode'] or '', 'alt_mobile': (u['alt_phone'] or '')[3:], 'lang': u['lang'] or '',
                'folios': json.loads(u['folios'] or '[]'), 'max_dp': self.st.max_dp_ids, 'plan': self.svc.plan_state(u), 'aliases': json.loads(u['aliases'] or '[]'), 'email_verified': bool(u['email_verified_at']),
                'phone_verified': bool(u['phone_verified_at']), 'channels': {'email': bool(u['ch_email']), 'sms': bool(u['ch_sms']), 'whatsapp': bool(u['ch_wa'])},
                'member_since': u['created_at'], 'states': STATES, 'langs': LANGS}

    def update_profile(self, u, p, ip=''):
        sets, args = {}, []
        names = {k: p.get(k, u[k]) for k in ('first_name', 'middle_name', 'last_name')}
        if any(k in p for k in names):
            first, last = _word(names['first_name'], 'First name'), _word(names['last_name'], 'Last name', req=bool(u['last_name']))
            middle = _word(names['middle_name'], 'Middle name', req=False)
            sets.update(first_name=first, middle_name=middle, last_name=last, name=clean_name(' '.join(x for x in (first, middle, last) if x)))
        if 'mobile' in p and not (u['phone'] == '' and not str(p['mobile']).strip()) and norm_phone(p['mobile']) != u['phone']:  # Google sign-ups start without a mobile number
            ph = norm_phone(p['mobile'])
            if self.db.one('SELECT 1 FROM subscribers WHERE phone=? AND password_hash IS NOT NULL AND id!=?', (ph, u['id'])):
                raise ApiError('That mobile number is already registered to another account.', 409)
            sets.update(phone=ph, phone_verified_at=None, otp_phone=None)
        opt = self._optional(p)  # validates what was sent; unsent keys are ignored below
        for k_in, k_db in (('dob', 'dob'), ('father_name', 'father_name'), ('address', 'address'), ('city', 'city'), ('state', 'state'), ('pincode', 'pincode'), ('alt_mobile', 'alt_phone'), ('lang', 'lang')):
            if k_in in p:
                sets[k_db] = opt[k_db]
        pan_new = None
        if str(p.get('pan') or '').strip():
            pan = clean_pan(p['pan'])
            if u['pan_hash']:
                if self.vault.index(pan) != u['pan_hash']:
                    raise ApiError('Your PAN is already saved and cannot be changed here. If it is wrong, write to %s.' % (self.st.support_email or 'us'), 403)
            else:
                if self.db.one('SELECT 1 FROM subscribers WHERE pan_hash=? AND password_hash IS NOT NULL AND id!=?', (self.vault.index(pan), u['id'])):
                    raise ApiError('This PAN is already registered with another account. If it is yours, write to %s.' % (self.st.support_email or 'us'), 409)
                sets.update(pan_hash=self.vault.index(pan), pan_enc=self.vault.seal(pan), pan_last4=pan[-4:])
                pan_new = True
        if 'folios' in p:
            new_f = clean_folios(p['folios'], self.st.max_dp_ids)
            old_f = json.loads(u['folios'] or '[]')
            if old_f and new_f != old_f:  # like the PAN, the demat / folio IDs are saved once and then locked
                raise ApiError('Your DP-Client IDs / folio numbers are already saved and cannot be changed here. If one is wrong, write to %s.' % (self.st.support_email or 'us'), 403)
            if not old_f:
                sets['folios'] = json.dumps(new_f)
        if 'aliases' in p:
            sets['aliases'] = json.dumps([clean_name(a) for a in p['aliases'] if str(a).strip()][:3])
        if sets:
            try:
                self.db.x('UPDATE subscribers SET %s WHERE id=?' % ','.join('%s=?' % k for k in sets), tuple(sets.values()) + (u['id'],))
            except sqlite3.IntegrityError:
                raise ApiError('That mobile number or PAN is already registered to another account.', 409)
            if pan_new:
                self._consent(u['id'], 'pan', 'grant', 'profile', ip)
            if 'phone' in sets:  # SMS / WhatsApp must not go to an unverified number
                self.db.x('UPDATE subscribers SET ch_sms=0, ch_wa=0 WHERE id=?', (u['id'],))
                for subj in ('sms', 'whatsapp'):
                    self._consent(u['id'], subj, 'withdraw', 'mobile_changed', ip)
            self.svc.match_subscriber(u['id'])
            if pan_new and u['email_verified_at']:  # the search starts the moment the PAN is saved, so the first alert goes out now
                self.svc.process_alerts(only_sub=u['id'])
                self.svc.dispatch_outbox()
        return self.profile(self._get(u['id']))

    # -------------------------------------------------------------- mobile OTP
    def phone_send_otp(self, u):
        if not u['phone']:
            raise ApiError('Add your mobile number above and save it first.')
        if u['phone_verified_at']:
            raise ApiError('Your mobile number is already verified.')
        if time.time() - (u['otp_sent_at'] or 0) < 60:
            raise ApiError('Please wait a minute before asking for a new code.', 429)
        otp = self.svc._otp()
        self.db.x('UPDATE subscribers SET otp_phone=?, otp_exp=?, otp_tries=0, otp_sent_at=? WHERE id=?', (self.svc._hash(u['id'], 'p', otp), time.time() + self.st.otp_ttl, time.time(), u['id']))
        ok, err = self.n.send('sms', u['phone'], '%s is your %s verification code. Valid for %d minutes.' % (otp, self.st.brand, self.st.otp_ttl // 60), kind='otp', vars={'otp': otp})
        if not ok:
            raise ApiError('We could not send the SMS. Please check the number and try again.', 502)
        return {'dev_otp': otp} if self.st.dev_mode else {}

    def phone_verify(self, u, otp):
        if u['phone_verified_at']:
            return {}
        if (u['otp_tries'] or 0) >= 5:
            raise ApiError('Too many wrong attempts. Please request a new code.', 429)
        if not u['otp_phone'] or time.time() > (u['otp_exp'] or 0):
            raise ApiError('The code has expired. Please request a new one.', 410)
        if not hmac.compare_digest(self.svc._hash(u['id'], 'p', str(otp).strip()), u['otp_phone']):
            self.db.x('UPDATE subscribers SET otp_tries=otp_tries+1 WHERE id=?', (u['id'],))
            raise ApiError('That code is not correct.')
        self.db.x('UPDATE subscribers SET phone_verified_at=?, otp_phone=NULL WHERE id=?', (now_iso(), u['id']))
        return {}

    # -------------------------------------------------------------- alert subscriptions (email / SMS / WhatsApp)
    def set_channels(self, u, ch, ip='', source='account'):
        cur = {'email': bool(u['ch_email']), 'sms': bool(u['ch_sms']), 'whatsapp': bool(u['ch_wa'])}
        new = {k: bool(ch[k]) if k in ch else cur[k] for k in cur}
        ps = self.svc.plan_state(u)
        for k in ('sms', 'whatsapp'):
            if new[k] and not cur[k] and not ps[k]:
                raise ApiError('%s alerts are included from the %s plan. Upgrade to switch them on.' % ('SMS' if k == 'sms' else 'WhatsApp', 'Silver' if k == 'sms' else 'Gold'), 403, need='upgrade')
        if (new['sms'] and not cur['sms'] or new['whatsapp'] and not cur['whatsapp']) and not u['phone_verified_at']:
            raise ApiError('Verify your mobile number first (we send a one-time code), then turn SMS / WhatsApp alerts on.', 400, need='verify_phone')
        self.db.x('UPDATE subscribers SET ch_email=?, ch_sms=?, ch_wa=? WHERE id=?', (int(new['email']), int(new['sms']), int(new['whatsapp']), u['id']))
        for k in cur:
            if new[k] != cur[k]:
                self._consent(u['id'], k, 'grant' if new[k] else 'withdraw', source, ip)
        return new

    def unsub_info(self, token):
        u = self.db.one('SELECT * FROM subscribers WHERE token=?', (token or '',))
        if not u:
            raise ApiError('This link is not valid.', 404)
        return {'email': mask_email(u['email']), 'phone': mask_phone(u['phone']), 'channels': {'email': bool(u['ch_email']), 'sms': bool(u['ch_sms']), 'whatsapp': bool(u['ch_wa'])},
                'has_account': bool(u['password_hash'])}

    def unsub_set(self, token, what, ip=''):
        """One-click opt-out from the link in every message. Turning things OFF only; turning on needs a sign-in."""
        u = self.db.one('SELECT * FROM subscribers WHERE token=?', (token or '',))
        if not u:
            raise ApiError('This link is not valid.', 404)
        if what not in ('email', 'sms', 'whatsapp', 'all'):
            raise ApiError('Choose what to turn off.')
        off = {'email': False, 'sms': False, 'whatsapp': False} if what == 'all' else {what: False}
        new = self.set_channels(u, off, ip, 'unsubscribe_link')
        return {'channels': new}

    # -------------------------------------------------------------- delete account
    def delete_account(self, u, password, ip=''):
        if not check_password(str(password or ''), u['password_hash']):
            raise ApiError('Your password is not correct.', 403)
        self.svc.delete_user_data(u['id'])
        return {'deleted': True}
