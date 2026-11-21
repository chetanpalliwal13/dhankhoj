import io, json, os, sys, tempfile, threading, time, unittest, urllib.request, urllib.error, datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['NO_PROXY'] = '127.0.0.1,localhost'
os.environ.pop('HTTP_PROXY', None); os.environ.pop('http_proxy', None)
import ingest, matcher as M
from config import Settings
from db import DB
from notify import Notifier
from service import Service, ApiError
import server as S

LINES = """Unpaid Dividend Details of 1st Interim Dividend for the FY 2026-27

DIVIDEND TYPE FOLIO NAME ADD1 ADD2 ADD3 ADD4 PINCODE HOLDING NET DIVIDEND
INT DIV 2026-27 IN30011811111111 RAMESH KUMAR GUPTA FLAT 4 SUNRISE APARTMENTS MUMBAI 400053 160 680.00
INT DIV 2026-27 1201090000012345 ANITA R DESAI H NO 7 GANDHI NAGAR PUNE 411001 10 42.50
INT DIV 2026-27 123456 MOHAMMED IQBAL KHAN DUBAI UAE 55 233.75
INT DIV 2026-27 IN30022822222222 SURESH PATEL 12 MG ROAD SURAT 395001 40 170.00

Unpaid Dividend Details of 1st Interim Dividend for the FY 2026-27
INT DIV 2026-27 IN30033833333333 PRIYA NAIR 5 SECTOR 9 KOCHI 682001 20 85.00
"""

def _w(p, s):
    with open(p, 'w') as f: f.write(s)

def mk(declared='2026-11-14', text=LINES, company='Test Co Ltd'):
    st = Settings(); st.db_path = ':memory:'; st.dev_mode = True; st.salt = 'testsalt'; st.admin_token = 'adm'; st.base_url = 'http://t'
    st.email_provider = st.sms_provider = st.wa_provider = 'console'
    db = DB(':memory:'); n = Notifier(st); n.sent.clear(); svc = Service(db, st, n)
    d = tempfile.mkdtemp(); p = os.path.join(d, 'l.txt'); _w(p, text)
    if company:
        res = ingest.ingest_file(db, company, p, declared_on=declared)
    return st, db, svc, res if company else None


class Parse(unittest.TestCase):
    def test_ingest_counts_and_meta(self):
        st, db, svc, r = mk()
        self.assertEqual(r['status'], 'ok'); self.assertEqual(r['rows'], 5); self.assertEqual(r['fy'], '2026-27'); self.assertEqual(r['dtype'], 'Interim')
        self.assertEqual(r['iepf_due_est'], (dt.date(2026, 11, 14) + dt.timedelta(days=37)).replace(year=2033).isoformat())
        row = db.one("SELECT * FROM records WHERE folio_key=?", ('IN30011811111111',)); self.assertEqual(row['pincode'], '400053'); self.assertEqual(row['holding'], 160); self.assertAlmostEqual(row['amount'], 680.0)
    def test_no_pincode_row(self):
        st, db, svc, r = mk(); row = db.one("SELECT * FROM records WHERE folio_key='123456'"); self.assertEqual(row['holding'], 55); self.assertAlmostEqual(row['amount'], 233.75)
    def test_duplicate_file_and_rows(self):
        st, db, svc, r = mk(); d = tempfile.mkdtemp(); p = os.path.join(d, 'again.txt'); _w(p, LINES)
        self.assertEqual(ingest.ingest_file(db, 'Test Co Ltd', p, declared_on='2026-11-14')['status'], 'duplicate')
    def test_csv(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, 'a.csv'); _w(p, 'FOLIO NO,NAME,ADDRESS 1,PINCODE,NO OF SHARES,AMOUNT (RS)\nIN30999,SITA RAM,12 ROAD JAIPUR,302001,10,"1,250.50"\n')
        st, db, svc, _ = mk(company=None); r = ingest.ingest_file(db, 'Csv Co', p, fy='2024-25', dtype='Final', declared_on='2024-09-01')
        self.assertEqual(r['rows'], 1); self.assertAlmostEqual(db.one('SELECT amount FROM records')['amount'], 1250.5)
    def test_bad_file(self):
        st, db, svc, _ = mk(company=None); d = tempfile.mkdtemp(); p = os.path.join(d, 'x.txt'); _w(p, 'nothing useful here\n')
        self.assertEqual(ingest.ingest_file(db, 'Zero Co', p)['status'], 'error')

class Match(unittest.TestCase):
    def setUp(self): self.st, self.db, self.svc, _ = mk()
    def find(self, name, pin='', folios=None, aliases=None): return M.find_matches(self.db, name, aliases or [], pin, folios or [])
    def test_exact_with_pin_is_high(self):
        r = self.find('Anita Desai', '411001'); self.assertEqual(r[0][1], 'high')
    def test_initial_and_order(self):
        self.assertTrue(self.find('Anita Rao Desai', '411001') or self.find('Desai Anita', '411001'))
        self.assertEqual(self.find('Desai Anita', '411001')[0][1], 'high')
    def test_typo(self):
        r = self.find('Rameesh Kumar Gupta', '400053'); self.assertTrue(r and r[0][1] in ('high', 'medium'))
    def test_wrong_pin_downgrades(self):
        r = self.find('Anita Desai', '999999'); self.assertTrue(all(c == 'low' for _, c, _ in r))
    def test_single_word_never_alerts(self):
        self.assertTrue(all(c == 'low' for _, c, _ in self.find('Desai')))
    def test_folio_always_high(self):
        r = self.find('Someone Else', folios=['IN30022822222222']); self.assertEqual(r[0][1], 'high')
    def test_no_false_positive(self):
        self.assertEqual(self.find('Zubin Mehta Roy', '400001'), [])
    def test_mask(self):
        self.assertEqual(M.mask_word('ANITA'), 'A****'); self.assertTrue(M.mask_folio('IN30011811111111').endswith('1111')); self.assertNotIn('IN3001', M.mask_folio('IN30011811111111'))



# ============================================================================ accounts, gating, billing (new)
import hashlib, hmac, http.cookiejar, sqlite3
from auth import Auth, Vault, hash_password, check_password, clean_pan, clean_password
from billing import Billing
from claims import Claims


def stack(**over):
    st, db, svc, _ = mk()
    for k, v in over.items():
        setattr(st, k, v)
    return st, db, svc, Auth(svc), Billing(svc), Claims(svc)


def payload(**kw):
    d = dict(first_name='Anita', last_name='Desai', mobile='98765 43210', email='a@x.in', password='Str0ng-pass!', consent=True); d.update(kw); return d


def token_of(r):
    return r['dev_link'].split('token=')[1]


PROFILE_KEYS = ('folios', 'aliases', 'dob', 'father_name', 'address', 'city', 'state', 'alt_mobile', 'lang')


def register(au, verify=True, phone=False, pan='ABCPD1234F', pincode='411001', **kw):
    """Sign up (name, mobile, email, password) and - like a real user - add PAN and the rest in the profile. pan=None leaves the PAN unset."""
    prof = {k: kw.pop(k) for k in PROFILE_KEYS if k in kw}
    if pan:
        prof['pan'] = pan
    if pincode:
        prof['pincode'] = pincode
    r = au.signup(payload(**kw))
    u = au._by_email(kw.get('email', 'a@x.in'))
    if prof:
        au.update_profile(u, prof)
    if verify:
        au.verify_email(token_of(r))
    if phone:
        au.db.x("UPDATE subscribers SET phone_verified_at='2026-01-01' WHERE id=?", (u['id'],))
    return au._get(u['id']), r


def add_companies(db, n=7, name='ANITA DESAI'):
    for i in range(n):
        d = tempfile.mkdtemp(); p = os.path.join(d, 'c%d.txt' % i)
        _w(p, 'INT DIV 2026-27 IN3009%d %s PUNE 411001 20 %d.00\n' % (i, name, 50 + i))
        ingest.ingest_file(db, 'Gate Co %d' % i, p, declared_on=(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat())


class Crypto(unittest.TestCase):
    def test_password_hash_roundtrip(self):
        h = hash_password('Correct-Horse-9'); self.assertTrue(check_password('Correct-Horse-9', h)); self.assertFalse(check_password('wrong', h)); self.assertNotIn('Correct', h)
        self.assertNotEqual(h, hash_password('Correct-Horse-9'))  # random salt
        self.assertFalse(check_password('x', 'garbage'))
    def test_vault_roundtrip_tamper_and_key(self):
        v = Vault('k1'); blob = v.seal('ABCPD1234F'); self.assertNotIn('ABCPD', blob); self.assertEqual(v.open(blob), 'ABCPD1234F')
        self.assertNotEqual(v.seal('ABCPD1234F'), blob)  # fresh nonce each time
        self.assertIsNone(Vault('other').open(blob)); self.assertIsNone(v.open(blob[:-3] + 'AAA')); self.assertIsNone(v.open('junk'))
        self.assertEqual(v.index('ABCPD1234F'), Vault('k1').index('ABCPD1234F')); self.assertNotEqual(v.index('ABCPD1234F'), Vault('k2').index('ABCPD1234F'))
    def test_pan_validation(self):
        self.assertEqual(clean_pan(' abcpd 1234f '), 'ABCPD1234F')
        for bad in ('ABCDE1234', 'ABCXD1234F', '1234567890', 'ABCPD12345', '', 'ABCPD1234FF'):
            with self.assertRaises(ApiError): clean_pan(bad)
    def test_password_rules(self):
        for bad in ('short1', '12345678', 'password123', 'x' * 129, 'ramesh-gupta-1'):
            with self.assertRaises(ApiError): clean_password(bad, 'Ramesh', 'Gupta')
        self.assertEqual(clean_password('a-fine-phrase-77'), 'a-fine-phrase-77')
    def test_env_file_inline_comments(self):
        import config
        d = tempfile.mkdtemp(); p = os.path.join(d, '.env'); _w(p, 'T_A=abc   # note\nT_B="quoted # keep"\nT_C=\nT_D=http://x/#frag\n')
        for k in 'ABCD': os.environ.pop('T_' + k, None)
        config._load_env(p); self.assertEqual((os.environ['T_A'], os.environ['T_B'], os.environ['T_C'], os.environ['T_D']), ('abc', 'quoted # keep', '', 'http://x/#frag'))


class Signup(unittest.TestCase):
    def setUp(self): self.st, self.db, self.svc, self.au, self.bl, self.cl = stack(); self.n = self.svc.n
    def test_required_fields_and_consent(self):
        for bad in (dict(consent=False), dict(first_name=''), dict(last_name=''), dict(mobile='12345'), dict(email='nope'), dict(password='abc'), dict(password='Anita-Desai-1'), dict(password='x9876543210y')):
            with self.assertRaises(ApiError, msg=str(bad)): self.au.signup(payload(**bad))
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM subscribers')['n'], 0)
    def test_signup_asks_only_the_basics_and_ignores_pan(self):
        r = self.au.signup(payload(pan='ABCPD1234F', folios=['IN30011811111111'], dob='1975-01-01')); u = self.au._by_email('a@x.in')
        self.assertEqual((u['pan_hash'], u['pan_enc'], u['pan_last4'], u['folios'], u['dob']), (None, None, None, '[]', None))  # PAN / IDs / optional details are profile-only
        self.assertEqual((u['ch_email'], u['ch_sms'], u['ch_wa']), (1, 0, 0))
    def test_creates_pending_account_and_emails_link(self):
        r = self.au.signup(payload()); u = self.au._by_email('a@x.in')
        self.assertEqual(u['status'], 'pending'); self.assertIsNone(u['email_verified_at']); self.assertEqual(u['name'], 'Anita Desai'); self.assertEqual(u['phone'], '+919876543210')
        m = [x for x in self.n.sent if x['channel'] == 'email'][-1]; self.assertIn('verify-email.html?token=', m['body']); self.assertEqual(self.db.one('SELECT COUNT(*) n FROM matches')['n'], 0)  # no matching before the link is clicked
    def test_pan_encrypted_at_rest_and_masked(self):
        u, _ = register(self.au); raw = json.dumps([dict(r) for r in self.db.q('SELECT * FROM subscribers')])
        self.assertNotIn('ABCPD1234F', raw); self.assertEqual(u['pan_last4'], '234F'); self.assertEqual(self.au.vault.open(u['pan_enc']), 'ABCPD1234F')
        p = self.au.profile(u); self.assertEqual(p['pan_masked'], 'XXXXXX234F'); self.assertNotIn('ABCPD1234F', json.dumps(p))
    def test_tokens_stored_hashed(self):
        r = self.au.signup(payload()); t = token_of(r); row = self.db.one('SELECT * FROM auth_tokens'); self.assertNotEqual(row['token_hash'], t); self.assertEqual(len(row['token_hash']), 64)
    def test_email_link_activates_matches_and_alerts(self):
        r = self.au.signup(payload()); u = self.au._by_email('a@x.in'); self.au.update_profile(u, {'pan': 'ABCPD1234F', 'pincode': '411001'}); self.n.sent.clear()
        v = self.au.verify_email(token_of(r)); self.assertFalse(v['already']); u = self.au._by_email('a@x.in'); self.assertEqual(u['status'], 'active')
        em = [m for m in self.n.sent if m['channel'] == 'email' and 'found for' in (m['subject'] or '')]; self.assertTrue(em); self.assertIn('dashboard.html', em[0]['body']); self.assertIn('unsubscribe.html?t=', em[0]['body'])
        self.assertFalse([m for m in self.n.sent if m['channel'] == 'sms'])
    def test_nothing_is_searched_until_pan_is_saved(self):
        u, r = register(self.au, pan=None); self.n.sent.clear()
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM matches')['n'], 0); me = self.svc.me(u); self.assertTrue(me['needs_pan']); self.assertEqual((me['likely'], me['total_likely']), ([], 0))
        self.au.update_profile(u, {'pan': 'ABCPD1234F', 'pincode': '411001'}); me = self.svc.me(self.au._get(u['id'])); self.assertFalse(me['needs_pan']); self.assertEqual(me['likely'][0]['company'], 'Test Co Ltd')
        self.assertTrue([m for m in self.n.sent if m['channel'] == 'email' and 'found for' in (m['subject'] or '')])  # first alert goes out as soon as the PAN is saved
    def test_link_single_use_but_double_click_ok(self):
        r = self.au.signup(payload()); t = token_of(r); self.au.verify_email(t); self.assertTrue(self.au.verify_email(t)['already'])
        with self.assertRaises(ApiError) as c: self.au.verify_email('not-a-token')
        self.assertEqual(c.exception.code, 410)
    def test_expired_link(self):
        r = self.au.signup(payload()); self.db.x('UPDATE auth_tokens SET exp=1')
        with self.assertRaises(ApiError) as c: self.au.verify_email(token_of(r))
        self.assertEqual(c.exception.code, 410)
    def test_resend_invalidates_old_link_and_is_quiet_for_strangers(self):
        r = self.au.signup(payload()); t1 = token_of(r); self.db.x('UPDATE auth_tokens SET created_at=1')  # skip the 60 s cooldown
        r2 = self.au.resend_verification('a@x.in'); self.assertTrue(r2)
        with self.assertRaises(ApiError): self.au.verify_email(t1)
        self.au.verify_email(token_of(r2)); n = len(self.n.sent); self.assertEqual(self.au.resend_verification('nobody@x.in'), {}); self.assertEqual(len(self.n.sent), n)
    def test_duplicates_rejected_without_saying_which(self):
        register(self.au)
        for kw in (dict(), dict(mobile='9111111111'), dict(email='b@x.in')):
            with self.assertRaises(ApiError) as c: self.au.signup(payload(**kw))
            self.assertEqual(c.exception.code, 409)
        with self.assertRaises(ApiError) as c: self.au.signup(payload(email='b@x.in'))  # new email, same mobile
        self.assertEqual(c.exception.code, 409); self.assertNotIn('mobile', c.exception.msg)
    def test_optional_fields_saved_and_listed(self):
        u, _ = register(self.au, dob='1975-08-21', father_name='Ravi Desai', address='H 7 Gandhi Nagar', city='Pune', state='Maharashtra', alt_mobile='9123456780', lang='Hindi', middle_name='Rao', folios=['IN30099'], aliases=['Anita Rao'])
        p = self.au.profile(u); self.assertEqual((p['dob'], p['father_name'], p['city'], p['state'], p['alt_mobile'], p['lang'], p['middle_name']), ('1975-08-21', 'Ravi Desai', 'Pune', 'Maharashtra', '9123456780', 'Hindi', 'Rao')); self.assertEqual(u['name'], 'Anita Rao Desai')
    def test_consent_log(self):
        r = self.au.signup(payload()); u = self.au._by_email('a@x.in')
        got = {(c['subject'], c['action']) for c in self.db.q('SELECT * FROM consents WHERE user_id=?', (u['id'],))}; self.assertEqual(got, {('terms', 'grant'), ('email', 'grant')})
        self.au.update_profile(u, {'pan': 'ABCPD1234F'}); self.assertTrue(self.db.one("SELECT 1 FROM consents WHERE subject='pan' AND action='grant' AND source='profile'"))
    def test_legacy_anonymous_subscriber_is_adopted(self):
        self.db.x("INSERT INTO subscribers(name,email,phone,status,token,created_at,verified_at) VALUES('Old Name','a@x.in','+919000000000','active','oldtok','2026-01-01','2026-01-01')")
        self.db.x("INSERT INTO subscribers(name,email,phone,status,token,created_at) VALUES('Other Name','a@x.in','+919000000001','active','oldtok2','2026-01-01')")
        u, _ = register(self.au); self.assertEqual(self.db.one("SELECT COUNT(*) n FROM subscribers WHERE email='a@x.in'")['n'], 1); self.assertNotEqual(u['token'], 'oldtok'); self.assertEqual(u['name'], 'Anita Desai')
    def test_migration_upgrades_old_database(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, 'old.db'); c = sqlite3.connect(p)
        c.execute("CREATE TABLE subscribers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, aliases TEXT DEFAULT '[]', email TEXT NOT NULL, phone TEXT NOT NULL, pincode TEXT, folios TEXT DEFAULT '[]', ch_email INTEGER DEFAULT 1, ch_sms INTEGER DEFAULT 1, ch_wa INTEGER DEFAULT 0, status TEXT DEFAULT 'pending', token TEXT UNIQUE, otp_email TEXT, otp_phone TEXT, otp_exp REAL, otp_tries INTEGER DEFAULT 0, otp_sent_at REAL DEFAULT 0, consent_at TEXT, created_at TEXT, verified_at TEXT)")
        c.execute("INSERT INTO subscribers(name,email,phone,status,token,verified_at) VALUES('A B','a@x.in','+911','active','t','2026-02-02')"); c.commit(); c.close()
        db = DB(p); r = db.one('SELECT * FROM subscribers'); self.assertEqual(r['email_verified_at'], '2026-02-02'); self.assertIsNone(r['password_hash']); DB(p)  # second open is a no-op


class SignIn(unittest.TestCase):
    def setUp(self): self.st, self.db, self.svc, self.au, self.bl, self.cl = stack(); self.u, _ = register(self.au)
    def test_login_logout_session(self):
        tok, u = self.au.login('A@X.in', 'Str0ng-pass!'); self.assertEqual(self.au.user_for(tok)['id'], u['id']); self.assertNotIn(tok, json.dumps([dict(r) for r in self.db.q('SELECT * FROM sessions')]))
        self.au.logout(tok); self.assertIsNone(self.au.user_for(tok)); self.assertIsNone(self.au.user_for('')); self.assertIsNone(self.au.user_for('junk'))
    def test_bad_credentials_same_message(self):
        msgs = set()
        for e, p in (('a@x.in', 'wrong-pass-1'), ('nobody@x.in', 'Str0ng-pass!'), ('not-an-email', 'x')):
            with self.assertRaises(ApiError) as c: self.au.login(e, p)
            self.assertEqual(c.exception.code, 401); msgs.add(c.exception.msg)
        self.assertEqual(len(msgs), 1)
    def test_lockout_after_ten_failures(self):
        for i in range(10):
            with self.assertRaises(ApiError): self.au.login('a@x.in', 'bad-pass-%d' % i)
        with self.assertRaises(ApiError) as c: self.au.login('a@x.in', 'Str0ng-pass!')
        self.assertEqual(c.exception.code, 429); self.db.x('UPDATE subscribers SET locked_until=0'); self.au.login('a@x.in', 'Str0ng-pass!')
    def test_session_expiry(self):
        tok, _ = self.au.login('a@x.in', 'Str0ng-pass!'); self.db.x('UPDATE sessions SET expires_at=1'); self.assertIsNone(self.au.user_for(tok))
    def test_forgot_and_reset(self):
        tok, _ = self.au.login('a@x.in', 'Str0ng-pass!'); self.n = self.svc.n; self.n.sent.clear()
        r = self.au.forgot('a@x.in'); t = token_of(r); self.assertTrue([m for m in self.n.sent if 'reset.html?token=' in m['body']]); self.assertTrue(self.au.check_reset_token(t))
        with self.assertRaises(ApiError): self.au.reset(t, 'short')  # weak password must not burn the link
        self.assertTrue(self.au.check_reset_token(t)); self.au.reset(t, 'Brand-New-Pass-5')
        self.assertFalse(self.au.check_reset_token(t)); self.assertIsNone(self.au.user_for(tok))  # signed out everywhere
        with self.assertRaises(ApiError) as c: self.au.reset(t, 'Another-Pass-77')
        self.assertEqual(c.exception.code, 410)
        with self.assertRaises(ApiError): self.au.login('a@x.in', 'Str0ng-pass!')
        self.au.login('a@x.in', 'Brand-New-Pass-5')
    def test_forgot_does_not_reveal_accounts(self):
        n = len(self.svc.n.sent); self.assertEqual(self.au.forgot('nobody@x.in'), {}); self.assertEqual(self.au.forgot('garbage'), {}); self.assertEqual(len(self.svc.n.sent), n)
    def test_reset_link_expires_and_new_one_replaces_old(self):
        t1 = token_of(self.au.forgot('a@x.in')); self.db.x('UPDATE auth_tokens SET created_at=1'); t2 = token_of(self.au.forgot('a@x.in'))
        with self.assertRaises(ApiError): self.au.reset(t1, 'Brand-New-Pass-5')
        self.db.x('UPDATE auth_tokens SET exp=1')
        with self.assertRaises(ApiError): self.au.reset(t2, 'Brand-New-Pass-5')
    def test_reset_confirms_unverified_email(self):
        u2, _ = register(self.au, verify=False, email='b@x.in', pan='XYZPD9999Z', mobile='9123456780'); self.assertEqual(u2['status'], 'pending')
        self.au.reset(token_of(self.au.forgot('b@x.in')), 'Brand-New-Pass-5'); self.assertEqual(self.au._get(u2['id'])['status'], 'active')
    def test_change_password_keeps_current_session_only(self):
        t1, u = self.au.login('a@x.in', 'Str0ng-pass!'); t2, _ = self.au.login('a@x.in', 'Str0ng-pass!')
        with self.assertRaises(ApiError) as c: self.au.change_password(u, 'wrong', 'Brand-New-Pass-5', t1)
        self.assertEqual(c.exception.code, 403); self.au.change_password(u, 'Str0ng-pass!', 'Brand-New-Pass-5', t1); self.assertTrue(self.au.user_for(t1)); self.assertIsNone(self.au.user_for(t2))


class Profile(unittest.TestCase):
    def setUp(self): self.st, self.db, self.svc, self.au, self.bl, self.cl = stack(); self.u, _ = register(self.au)
    def test_update_and_rematch(self):
        p = self.au.update_profile(self.u, {'first_name': 'Priya', 'last_name': 'Nair', 'pincode': '682001'}); self.assertEqual(p['first_name'], 'Priya')
        self.assertEqual(self.svc.me(self.au._get(self.u['id']))['likely'][0]['company'], 'Test Co Ltd'); self.assertEqual(self.db.one('SELECT name FROM subscribers')['name'], 'Priya Nair')
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM matches')['n'], 1)  # the old Anita match was dropped
    def test_pan_is_set_once_and_email_cannot_change(self):
        with self.assertRaises(ApiError) as c: self.au.update_profile(self.u, {'pan': 'ZZZPD9999Z'})
        self.assertEqual(c.exception.code, 403); self.au.update_profile(self.u, {'pan': 'abcpd1234f', 'email': 'evil@x.in', 'city': 'Pune'})  # same PAN again is a no-op
        u = self.au._get(self.u['id']); self.assertEqual((u['pan_last4'], u['email'], u['city']), ('234F', 'a@x.in', 'Pune'))
    def test_pan_must_be_valid_and_unique(self):
        u2, _ = register(self.au, email='b@x.in', pan=None, mobile='9123456780')
        with self.assertRaises(ApiError): self.au.update_profile(u2, {'pan': 'BAD'})
        with self.assertRaises(ApiError) as c: self.au.update_profile(u2, {'pan': 'ABCPD1234F'})
        self.assertEqual(c.exception.code, 409); self.assertIsNone(self.au._get(u2['id'])['pan_hash']); self.au.update_profile(u2, {'pan': 'XYZPD9999Z'}); self.assertTrue(self.au._get(u2['id'])['pan_hash'])
    def test_up_to_five_dp_ids_normalised_and_deduplicated(self):
        p = self.au.update_profile(self.u, {'folios': ['in300118-11111111', 'IN30011811111111', ' 1208 1600 0012 3456 ', '', 'FOLIO 77']}); self.assertEqual(p['folios'], ['IN30011811111111', '1208160000123456', 'FOLIO77']); self.assertEqual(p['max_dp'], 5)
        with self.assertRaises(ApiError) as c: self.au.update_profile(self.au._get(self.u['id']), {'folios': ['AAAA1', 'BBBB2', 'CCCC3', 'DDDD4', 'EEEE5']})
        self.assertIn('already saved', c.exception.msg)  # once saved the IDs are locked
        self.assertEqual(json.loads(self.au._get(self.u['id'])['folios']), ['IN30011811111111', '1208160000123456', 'FOLIO77'])
    def test_too_many_and_bad_ids_rejected_on_first_save(self):
        u, _ = register(self.au, email='g@x.in', pan='QWEPD1111Q', mobile='9123456781', pincode=None)
        with self.assertRaises(ApiError) as c: self.au.update_profile(u, {'folios': ['AAAA1', 'BBBB2', 'CCCC3', 'DDDD4', 'EEEE5', 'FFFF6']})
        self.assertIn('up to 5', c.exception.msg)
        with self.assertRaises(ApiError): self.au.update_profile(u, {'folios': ['ab']})
        self.assertEqual(self.au._get(u['id'])['folios'], '[]')
    def test_ids_locked_after_first_save_but_same_list_is_fine(self):
        self.au.update_profile(self.u, {'folios': ['AAAA1']})
        self.au.update_profile(self.au._get(self.u['id']), {'folios': ['aaaa1']})  # unchanged -> no error
        with self.assertRaises(ApiError) as c: self.au.update_profile(self.au._get(self.u['id']), {'folios': ['AAAA1', 'ZZZZ9']})
        self.assertEqual(c.exception.code, 403)
    def test_pan_locked(self):
        with self.assertRaises(ApiError) as c: self.au.update_profile(self.au._get(self.u['id']), {'pan': 'QWEPD1111Q'})
        self.assertEqual(c.exception.code, 403)
    def test_dp_id_in_profile_finds_the_holding(self):
        u, _ = register(self.au, email='f@x.in', pan='XYZPD9999Z', mobile='9123456780', pincode=None); self.au.update_profile(u, {'first_name': 'Someone', 'last_name': 'Else'})
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM matches WHERE sub_id=?', (u['id'],))['n'], 0)
        self.au.update_profile(self.au._get(u['id']), {'folios': ['IN30022822222222']}); m = self.svc._match_rows(u['id']); self.assertEqual((len(m), m[0]['conf']), (1, 'high'))
    def test_pan_printed_in_a_list_is_a_high_match_even_when_the_name_differs(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, 'p.txt'); _w(p, 'INT DIV 2026-27 IN30777 KUMAR SURESH BABU QQQPS7777Q CHENNAI 600001 10 500.00\n'); ingest.ingest_file(self.db, 'Pan Co', p, declared_on='2026-01-01')
        u, _ = register(self.au, email='q@x.in', pan='QQQPS7777Q', mobile='9123456780', pincode=None); u = self.au._get(u['id']); self.au.update_profile(u, {'first_name': 'S', 'last_name': 'Babu'})
        rows = [m for m in self.svc._match_rows(u['id']) if m['company'] == 'Pan Co']; self.assertEqual([m['conf'] for m in rows], ['high'])
        raw = json.dumps(self.svc.me(self.au._get(u['id'])), default=str); self.assertNotIn('QQQPS7777Q', raw)
    def test_pan_backfill_indexes_old_records(self):
        self.db.x("INSERT INTO records(list_id,company_id,folio,folio_key,blob,amount,rowhash) VALUES(1,1,'X9','X9','OLD ROW NAME ZZZPD5555Z',5,'rh1')"); self.db.meta_set('pan_tok_v1', ''); self.db.x("DELETE FROM meta WHERE k='pan_tok_v1'")
        self.assertEqual(ingest.backfill_pan_tokens(self.db), 1); self.assertEqual(ingest.backfill_pan_tokens(self.db), 0); self.assertTrue(self.db.one("SELECT 1 FROM rec_tok WHERE token='ZZZPD5555Z'"))
    def test_mobile_change_resets_verification_and_channels(self):
        self.db.x("UPDATE subscribers SET phone_verified_at='x', ch_sms=1, ch_wa=1 WHERE id=?", (self.u['id'],))
        self.au.update_profile(self.au._get(self.u['id']), {'mobile': '9123456780'}); u = self.au._get(self.u['id']); self.assertEqual((u['phone'], u['phone_verified_at'], u['ch_sms'], u['ch_wa']), ('+919123456780', None, 0, 0))
    def test_mobile_taken(self):
        register(self.au, email='b@x.in', pan='XYZPD9999Z', mobile='9123456780')
        with self.assertRaises(ApiError) as c: self.au.update_profile(self.u, {'mobile': '9123456780'})
        self.assertEqual(c.exception.code, 409)
    def test_unsent_optional_fields_untouched(self):
        self.au.update_profile(self.u, {'city': 'Pune'}); self.au.update_profile(self.au._get(self.u['id']), {'state': 'Goa'}); u = self.au._get(self.u['id']); self.assertEqual((u['city'], u['state']), ('Pune', 'Goa'))
    def test_phone_otp(self):
        r = self.au.phone_send_otp(self.u); otp = r['dev_otp']; self.assertEqual(len(otp), 6); u = self.au._get(self.u['id']); self.assertNotIn(otp, u['otp_phone'])
        with self.assertRaises(ApiError) as c: self.au.phone_send_otp(u)
        self.assertEqual(c.exception.code, 429)
        with self.assertRaises(ApiError): self.au.phone_verify(u, '000000')
        self.au.phone_verify(self.au._get(u['id']), otp); self.assertTrue(self.au._get(u['id'])['phone_verified_at'])
    def test_phone_otp_lockout_and_expiry(self):
        otp = self.au.phone_send_otp(self.u)['dev_otp']
        for i in range(5):
            with self.assertRaises(ApiError): self.au.phone_verify(self.au._get(self.u['id']), '000000')
        with self.assertRaises(ApiError) as c: self.au.phone_verify(self.au._get(self.u['id']), otp)
        self.assertEqual(c.exception.code, 429); self.db.x('UPDATE subscribers SET otp_tries=0, otp_exp=1')
        with self.assertRaises(ApiError) as c: self.au.phone_verify(self.au._get(self.u['id']), otp)
        self.assertEqual(c.exception.code, 410)


class Channels(unittest.TestCase):
    def setUp(self): self.st, self.db, self.svc, self.au, self.bl, self.cl = stack(); self.u, _ = register(self.au); self.n = self.svc.n
    def test_sms_and_whatsapp_need_verified_mobile(self):
        self.bl.admin_grant('a@x.in', 'gold', 30)
        for ch in ('sms', 'whatsapp'):
            with self.assertRaises(ApiError) as c: self.au.set_channels(self.au._get(self.u['id']), {ch: True})
            self.assertEqual(c.exception.extra.get('need'), 'verify_phone')
        self.db.x("UPDATE subscribers SET phone_verified_at='x'"); self.assertTrue(self.au.set_channels(self.au._get(self.u['id']), {'sms': True, 'whatsapp': True})['whatsapp'])
    def test_channels_depend_on_the_plan(self):
        self.db.x("UPDATE subscribers SET phone_verified_at='x'")
        for ch in ('sms', 'whatsapp'):  # Free: email only
            with self.assertRaises(ApiError) as c: self.au.set_channels(self.au._get(self.u['id']), {ch: True})
            self.assertEqual(c.exception.extra.get('need'), 'upgrade')
        self.bl.admin_grant('a@x.in', 'silver', 30); self.assertTrue(self.au.set_channels(self.au._get(self.u['id']), {'sms': True})['sms'])
        with self.assertRaises(ApiError) as c: self.au.set_channels(self.au._get(self.u['id']), {'whatsapp': True})
        self.assertIn('Gold', c.exception.msg); self.bl.admin_grant('a@x.in', 'gold', 30); self.assertTrue(self.au.set_channels(self.au._get(self.u['id']), {'whatsapp': True})['whatsapp'])
        self.db.x("UPDATE subscribers SET plan_until='2020-01-01'"); self.assertFalse(self.au.set_channels(self.au._get(self.u['id']), {'sms': False})['sms'])  # switching off always works
    def test_expired_plan_stops_sms_and_whatsapp_but_not_email(self):
        self.db.x("UPDATE subscribers SET phone_verified_at='x', ch_sms=1, ch_wa=1"); add_companies(self.db, 1); self.n.sent.clear(); self.db.x('UPDATE matches SET notified=0'); self.svc.rematch_all(); self.svc.tick()
        self.assertEqual({m['channel'] for m in self.n.sent}, {'email'})  # flags are on, the Free plan does not include them
    def test_all_off_is_allowed_and_logged(self):
        self.au.set_channels(self.u, {'email': False}); self.assertEqual(self.db.one('SELECT ch_email FROM subscribers')['ch_email'], 0)
        self.assertTrue(self.db.one("SELECT 1 FROM consents WHERE subject='email' AND action='withdraw' AND source='account'"))
    def test_alerts_follow_channels(self):
        self.bl.admin_grant('a@x.in', 'gold', 30); self.db.x("UPDATE subscribers SET phone_verified_at='x', ch_sms=1, ch_wa=1"); add_companies(self.db, 1); self.n.sent.clear(); self.db.x('UPDATE matches SET notified=0'); self.svc.rematch_all(); self.svc.tick()
        chs = {m['channel'] for m in self.n.sent}; self.assertEqual(chs, {'email', 'sms', 'whatsapp'}); wa = [m for m in self.n.sent if m['channel'] == 'whatsapp'][0]; self.assertIn('unsubscribe.html?t=', wa['body']); self.assertNotIn('Reply STOP', wa['body'])
        self.n.sent.clear(); self.au.set_channels(self.au._get(self.u['id']), {'email': False, 'sms': False, 'whatsapp': False}); add_companies2 = self.db.x('UPDATE matches SET notified=0'); self.svc.tick(); self.assertEqual(self.n.sent, [])
    def test_unsubscribe_link_turns_off_only(self):
        self.db.x("UPDATE subscribers SET phone_verified_at='x', ch_sms=1, ch_wa=1"); tok = self.db.one('SELECT token FROM subscribers')['token']
        self.assertEqual(self.au.unsub_info(tok)['channels'], {'email': True, 'sms': True, 'whatsapp': True})
        self.assertEqual(self.au.unsub_set(tok, 'sms')['channels'], {'email': True, 'sms': False, 'whatsapp': True}); self.assertEqual(self.au.unsub_set(tok, 'all')['channels'], {'email': False, 'sms': False, 'whatsapp': False})
        self.assertTrue(self.db.one("SELECT 1 FROM consents WHERE source='unsubscribe_link'"))
        with self.assertRaises(ApiError): self.au.unsub_set(tok, 'bogus')
        with self.assertRaises(ApiError): self.au.unsub_info('nope')
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM subscribers')['n'], 1)  # the link never deletes the account
    def test_delete_account_removes_everything_keeps_payments_anonymous(self):
        tok, u = self.au.login('a@x.in', 'Str0ng-pass!'); self.bl.admin_grant('a@x.in', 'silver', 30); self.au.set_channels(u, {'email': False})
        with self.assertRaises(ApiError) as c: self.au.delete_account(u, 'wrong')
        self.assertEqual(c.exception.code, 403); self.au.delete_account(u, 'Str0ng-pass!')
        for t in ('subscribers', 'matches', 'reminders', 'outbox', 'sessions', 'auth_tokens', 'unlocks', 'consents'): self.assertEqual(self.db.one('SELECT COUNT(*) n FROM %s' % t)['n'], 0, t)
        p = self.db.one('SELECT * FROM payments'); self.assertIsNone(p['user_id'])
    def test_unconfirmed_accounts_purged_after_48h(self):
        self.au.signup(payload(email='c@x.in', pan='QQQPD1111Q', mobile='9000011111')); self.db.x("UPDATE subscribers SET created_at='2000-01-01T00:00:00' WHERE email='c@x.in'"); self.svc.purge()
        self.assertIsNone(self.db.one("SELECT 1 FROM subscribers WHERE email='c@x.in'")); self.assertEqual(self.db.one("SELECT COUNT(*) n FROM auth_tokens WHERE user_id NOT IN (SELECT id FROM subscribers)")['n'], 0)



class Gating(unittest.TestCase):
    def setUp(self):
        self.st, self.db, self.svc, self.au, self.bl, self.cl = stack(); add_companies(self.db, 7); self.n = self.svc.n; self.n.sent.clear(); self.u, _ = register(self.au)
    def me(self): return self.svc.me(self.au._get(self.u['id']))
    def test_first_five_free_soonest_deadline_first(self):
        me = self.me(); names = {i['company'] for i in me['likely']}; self.assertEqual(names, {'Gate Co %d' % i for i in range(5)})
        self.assertEqual((me['plan']['used'], me['locked']['companies'], me['locked']['entries'], me['locked']['likely_entries']), (5, 3, 3, 3)); self.assertTrue(me['locked']['amount_band'])
    def test_locked_companies_never_leak(self):
        raw = json.dumps(self.me()); 
        for n in ('Gate Co 5', 'Gate Co 6', 'Test Co Ltd', 'IN30095', 'IN30096'): self.assertNotIn(n, raw)
    def test_free_slots_are_never_taken_back(self):
        before = {i['company'] for i in self.me()['likely']}; d = tempfile.mkdtemp(); p = os.path.join(d, 'z.txt'); _w(p, 'INT DIV 2026-27 IN30999 ANITA DESAI PUNE 411001 20 99999.00\n')
        ingest.ingest_file(self.db, 'Urgent Rich Co', p, declared_on='2019-01-01'); self.svc.tick(); after = {i['company'] for i in self.me()['likely']}; self.assertEqual(before, after)
    def test_paid_plan_unlocks_everything_then_falls_back_to_free_five(self):
        self.bl.admin_grant('a@x.in', 'platinum', 30); me = self.me(); self.assertEqual(len(me['likely']), 8); self.assertEqual(me['locked']['entries'], 0); self.assertTrue(me['plan']['active']); self.assertEqual(me['plan']['tier'], 'platinum')
        self.db.x("UPDATE subscribers SET plan_until=?", ((dt.date.today() - dt.timedelta(days=1)).isoformat(),)); me = self.me(); self.assertEqual(len(me['likely']), 5); self.assertFalse(me['plan']['active']); self.assertTrue(me['plan']['expired_on']); self.assertEqual(me['plan']['tier'], 'free')
    def test_tier_company_caps_and_fall_back_to_free(self):
        self.st.tiers['silver']['companies'] = 6; self.bl.admin_grant('a@x.in', 'silver', 30); me = self.me(); self.assertEqual((len(me['likely']), me['locked']['companies'], me['plan']['used'], me['plan']['companies']), (6, 2, 6, 6))
        self.bl.admin_grant('a@x.in', 'gold', 30); self.st.tiers['gold']['companies'] = 7; me = self.me(); self.assertEqual((len(me['likely']), me['locked']['companies']), (7, 1))  # the slots already shown stay, one more is added
        self.bl.admin_grant('a@x.in', 'platinum', 30); self.assertEqual(len(self.me()['likely']), 8)
        self.db.x("UPDATE subscribers SET plan_until='2020-01-01'"); free = {i['company'] for i in self.me()['likely']}; self.assertEqual(len(free), 5); self.assertEqual(free, {'Gate Co %d' % i for i in range(5)})  # back to the original free five
    def test_downgrade_shows_only_what_the_lower_tier_allows(self):
        self.st.tiers['silver']['companies'] = 6; self.st.tiers['gold']['companies'] = 7; self.bl.admin_grant('a@x.in', 'gold', 30); self.assertEqual(len(self.me()['likely']), 7)
        self.db.x("UPDATE subscribers SET plan_tier='silver'"); self.assertEqual(len(self.me()['likely']), 6)
    def test_plans_bought_before_tiers_existed_count_as_platinum(self):
        self.db.x("UPDATE subscribers SET plan_until=?, plan_tier=NULL", ((dt.date.today() + dt.timedelta(days=20)).isoformat(),)); ps = self.svc.plan_state(self.au._get(self.u['id'])); self.assertEqual((ps['tier'], ps['companies']), ('platinum', None)); self.assertEqual(len(self.me()['likely']), 8)
    def test_alert_shows_only_unlocked_and_nudges(self):
        self.db.x('UPDATE matches SET notified=0'); self.n.sent.clear(); self.svc.tick()
        em = [m for m in self.n.sent if m['channel'] == 'email' and 'found for' in (m['subject'] or '')][0]; self.assertIn('Gate Co 0', em['body']); self.assertNotIn('Gate Co 6', em['body']); self.assertNotIn('Test Co Ltd', em['body'])
        self.assertIn('3 more companies', em['body']); self.assertIn('/upgrade.html', em['body']); self.assertIn('8 possible', em['subject'])
    def test_alert_for_paid_user_lists_all(self):
        self.bl.admin_grant('a@x.in', 'platinum', 30); self.db.x('UPDATE matches SET notified=0'); self.n.sent.clear(); self.svc.tick()
        em = [m for m in self.n.sent if m['channel'] == 'email' and 'found for' in (m['subject'] or '')][0]; self.assertIn('Gate Co 6', em['body']); self.assertNotIn('more compan', em['body'])
    def test_expert_help_cannot_include_locked_entries(self):
        vis = {i['id'] for i in self.me()['likely']}; locked = [m['mid'] for m in self.svc._match_rows(self.u['id']) if m['mid'] not in vis]; self.assertEqual(len(locked), 3)
        with self.assertRaises(ApiError): self.cl.create(self.au._get(self.u['id']), {'match_ids': [locked[0]], 'consent': True})
        self.cl.create(self.au._get(self.u['id']), {'match_ids': [next(iter(vis))], 'consent': True})
    def test_editing_profile_releases_free_slots(self):
        self.au.update_profile(self.au._get(self.u['id']), {'first_name': 'Priya', 'last_name': 'Nair', 'pincode': '682001'}); me = self.me(); self.assertEqual([i['company'] for i in me['likely']], ['Test Co Ltd']); self.assertEqual(me['plan']['used'], 1)
    def test_public_check_is_capped_to_free_size(self):
        r = self.svc.check('Anita Desai', '411001'); self.assertEqual((len(r['results']), r['more']), (5, 3)); self.assertIn('5 companies', r['note'])
    def test_each_user_has_their_own_five(self):
        u2, _ = register(self.au, email='b@x.in', pan='XYZPD9999Z', mobile='9123456780'); self.assertEqual(len(self.svc.me(u2)['likely']), 5)


class Reminders(unittest.TestCase):
    def test_stages_sent_once_and_smallest(self):
        due = (dt.date.today() + dt.timedelta(days=25)).isoformat()
        st, db, svc, au, bl, cl = stack(); db.x('UPDATE lists SET iepf_due=?', (due,)); register(au)
        st_rows = [r['stage'] for r in db.q('SELECT stage FROM reminders')]; self.assertIn(30, st_rows); self.assertIn(365, st_rows)  # skipped bigger stages are marked
        n1 = len(svc.n.sent); svc.tick(); self.assertEqual(len(svc.n.sent), n1)  # no repeat
        db.x('UPDATE lists SET iepf_due=?', ((dt.date.today() + dt.timedelta(days=5)).isoformat(),)); svc.tick()
        self.assertTrue(any('5 days' in (m['subject'] or '') for m in svc.n.sent))
    def test_passed_deadline_mentions_iepf5(self):
        st, db, svc, au, bl, cl = stack(); db.x("UPDATE lists SET iepf_due='2020-01-01'"); register(au)
        self.assertTrue(any('IEPF-5' in m['body'] for m in svc.n.sent))
    def test_reminders_skip_locked_companies(self):
        st, db, svc, au, bl, cl = stack(); add_companies(db, 7); db.x("UPDATE lists SET iepf_due=?", ((dt.date.today() + dt.timedelta(days=25)).isoformat(),)); svc.n.sent.clear(); register(au)
        rem = [m for m in svc.n.sent if m['channel'] == 'email' and 'days left' in (m['subject'] or '')]; self.assertTrue(rem)
        for hidden in ('Gate Co 0', 'Gate Co 1', 'Test Co Ltd'): self.assertNotIn(hidden, rem[0]['body'])  # same deadline for all, so the 5 largest amounts are the free ones; the rest stay out of reminders


class ClaimsTest(unittest.TestCase):
    def setUp(self):
        self.st, self.db, self.svc, self.au, self.bl, self.cl = stack(); self.u, _ = register(self.au); self.sid = self.u['id']
        self.mid = self.svc.me(self.u)['likely'][0]['id']
    def expert(self, status='verified'):
        self.cl.register_expert(dict(name='Ravi Kumar', profession='Company Secretary', membership_no='A12345', city='Pune', email='ravi@x.in', phone='9811122233', consent=True)); self.cl.admin_set_expert(1, status)
    def test_expert_register_validation(self):
        for bad in (dict(consent=False), dict(profession='Plumber'), dict(membership_no=''), dict(phone='1')):
            d = dict(name='Ravi Kumar', profession='Chartered Accountant', membership_no='1', city='X', email='r@x.in', phone='9811122233', consent=True); d.update(bad)
            with self.assertRaises(ApiError): self.cl.register_expert(d)
    def test_panel_lists_only_verified(self):
        self.expert('pending'); self.assertEqual(self.cl.public_panel(), []); self.cl.admin_set_expert(1, 'verified'); self.assertEqual(self.cl.public_panel()[0]['membership_no'], 'A12345')
        self.cl.admin_set_expert(1, 'suspended'); self.assertEqual(self.cl.public_panel(), [])
    def test_full_lifecycle(self):
        cid = self.cl.create(self.u, {'match_ids': [self.mid], 'consent': True, 'notes': 'lost certificate'})['id']
        self.assertEqual(self.cl.mine(self.sid)[0]['status'], 'new')
        self.cl.admin_update(cid, {'quote_amount': '2500', 'quote_note': 'fixed fee'}); self.assertEqual(self.cl.mine(self.sid)[0]['status'], 'quoted')
        self.assertTrue(self.db.one("SELECT 1 FROM outbox WHERE kind='claim' AND status='pending' AND subject LIKE '%update%'"))
        self.cl.respond(self.u, cid, True); self.assertEqual(self.cl.mine(self.sid)[0]['status'], 'accepted')
        with self.assertRaises(ApiError): self.cl.admin_update(cid, {'status': 'assigned', 'expert_id': 1})  # no expert yet
        self.expert(); self.cl.admin_update(cid, {'status': 'assigned', 'expert_id': 1}); self.assertEqual(self.cl.mine(self.sid)[0]['expert']['name'], 'Ravi Kumar')
        self.cl.admin_update(cid, {'status': 'completed'}); self.assertEqual(self.cl.mine(self.sid)[0]['status'], 'completed')
    def test_consent_and_ownership(self):
        with self.assertRaises(ApiError): self.cl.create(self.u, {'match_ids': [self.mid], 'consent': False})
        with self.assertRaises(ApiError): self.cl.create(self.u, {'match_ids': [], 'consent': True})
        with self.assertRaises(ApiError): self.cl.create(self.u, {'match_ids': [99999], 'consent': True})
    def test_cannot_accept_without_quote_or_other_users_claim(self):
        cid = self.cl.create(self.u, {'match_ids': [self.mid], 'consent': True})['id']
        with self.assertRaises(ApiError): self.cl.respond(self.u, cid, True)
        u2, _ = register(self.au, email='b@x.in', pan='XYZPD9999Z', mobile='9123456780')
        with self.assertRaises(ApiError): self.cl.respond(u2, cid, False)
        with self.assertRaises(ApiError): self.cl.create(u2, {'match_ids': [self.mid], 'consent': True})  # someone else's match id
    def test_account_deletion_deletes_claims(self):
        self.cl.create(self.u, {'match_ids': [self.mid], 'consent': True}); self.au.delete_account(self.u, 'Str0ng-pass!'); self.assertEqual(self.db.one('SELECT COUNT(*) n FROM claim_requests')['n'], 0)
    def test_quote_must_be_number(self):
        cid = self.cl.create(self.u, {'match_ids': [self.mid], 'consent': True})['id']
        with self.assertRaises(ApiError): self.cl.admin_update(cid, {'quote_amount': 'abc'})


class RzMock(BaseHTTPRequestHandler):
    log = []; fail = False
    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0); body = self.rfile.read(n).decode(); RzMock.log.append((self.path, dict(self.headers), body))
        if RzMock.fail: b = b'{"error":"down"}'; self.send_response(500)
        else: b = json.dumps({'id': 'order_T%d' % len(RzMock.log), 'amount': json.loads(body)['amount']}).encode(); self.send_response(200)
        self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass


def rz_sig(secret, data): return hmac.new(secret.encode(), data if isinstance(data, bytes) else data.encode(), hashlib.sha256).hexdigest()


class Billing_(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), RzMock); threading.Thread(target=cls.srv.serve_forever, daemon=True).start(); cls.base = 'http://127.0.0.1:%d' % cls.srv.server_port
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def setUp(self):
        RzMock.log.clear(); RzMock.fail = False
        self.st, self.db, self.svc, self.au, self.bl, self.cl = stack(pay_provider='razorpay', razorpay_key_id='rzp_test_K', razorpay_key_secret='SECRET', razorpay_webhook_secret='WHSEC', razorpay_base=self.base, upi_vpa='dk@bank')
        self.u, _ = register(self.au); self.n = self.svc.n
    def fresh(self): return self.au._get(self.u['id'])
    def order(self, tier='gold', period='yearly'): return self.bl.create_order(self.fresh(), tier, period)
    def paid_sig(self, o, pay='pay_1'): return {'razorpay_order_id': o['order_id'], 'razorpay_payment_id': pay, 'razorpay_signature': rz_sig('SECRET', o['order_id'] + '|' + pay)}
    def test_plan_info_has_no_secrets(self):
        raw = json.dumps(self.bl.plan_info()); self.assertNotIn('SECRET', raw); self.assertNotIn('WHSEC', raw); self.assertEqual(self.bl.plan_info()['gateway'], 'razorpay'); self.assertTrue(self.bl.plan_info()['upi'])
    def test_order_uses_server_price_and_basic_auth(self):
        o = self.order(); p, h, b = RzMock.log[0]; self.assertEqual(p, '/v1/orders'); self.assertEqual(json.loads(b)['amount'], 95000); self.assertTrue(h['Authorization'].startswith('Basic '))
        self.assertEqual((o['key_id'], o['amount_paise'], o['order_id'].startswith('order_')), ('rzp_test_K', 95000, True)); self.assertNotIn('SECRET', json.dumps(o)); self.assertEqual(o['prefill']['email'], 'a@x.in')
    def test_gateway_down_is_a_clean_error(self):
        RzMock.fail = True
        with self.assertRaises(ApiError) as c: self.order()
        self.assertEqual(c.exception.code, 502); self.assertEqual(self.db.one('SELECT status FROM payments')['status'], 'failed')
    def test_confirm_checks_signature_then_grants_once(self):
        o = self.order(); bad = self.paid_sig(o); bad['razorpay_signature'] = '0' * 64
        with self.assertRaises(ApiError): self.bl.confirm_checkout(self.fresh(), bad)
        self.assertIsNone(self.fresh()['plan_until']); self.assertEqual(self.bl.confirm_checkout(self.fresh(), self.paid_sig(o)), {'paid': True}); until = self.fresh()['plan_until']
        self.assertEqual(until, (dt.date.today() + dt.timedelta(days=365)).isoformat()); self.bl.confirm_checkout(self.fresh(), self.paid_sig(o)); self.assertEqual(self.fresh()['plan_until'], until)  # replay = no extra days
        p = self.db.one('SELECT * FROM payments'); self.assertEqual((p['status'], p['provider_payment_id'], p['amount_paise'], p['tier'], p['period']), ('paid', 'pay_1', 95000, 'gold', 'yearly')); self.assertEqual(self.fresh()['plan_tier'], 'gold'); self.assertTrue(p['receipt_no'].startswith('DKR-'))
        self.assertTrue([m for m in self.n.sent if 'receipt' in (m['subject'] or '')])
    def test_cannot_confirm_someone_elses_order(self):
        o = self.order(); u2, _ = register(self.au, email='b@x.in', pan='XYZPD9999Z', mobile='9123456780')
        with self.assertRaises(ApiError) as c: self.bl.confirm_checkout(u2, self.paid_sig(o))
        self.assertEqual(c.exception.code, 404)
    def event(self, o, amount=95000, ev='payment.captured', pay='pay_7'): return json.dumps({'event': ev, 'payload': {'payment': {'entity': {'id': pay, 'order_id': o['order_id'], 'amount': amount, 'method': 'upi'}}}}).encode()
    def test_webhook_grants_when_browser_never_returns(self):
        o = self.order(); raw = self.event(o); self.bl.webhook_razorpay(raw, rz_sig('WHSEC', raw)); self.assertTrue(self.fresh()['plan_until']); self.assertEqual(self.db.one('SELECT method FROM payments')['method'], 'upi')
    def test_webhook_and_browser_together_grant_once(self):
        o = self.order(); self.bl.confirm_checkout(self.fresh(), self.paid_sig(o, 'pay_7')); until = self.fresh()['plan_until']; raw = self.event(o); self.bl.webhook_razorpay(raw, rz_sig('WHSEC', raw)); self.assertEqual(self.fresh()['plan_until'], until)
    def test_webhook_rejects_bad_signature_wrong_amount_unknown_order(self):
        o = self.order(); raw = self.event(o)
        for sig in ('', 'bad', rz_sig('WRONG', raw)):
            with self.assertRaises(ApiError): self.bl.webhook_razorpay(raw, sig)
        self.assertIsNone(self.fresh()['plan_until'])
        raw2 = self.event(o, amount=100); self.assertEqual(self.bl.webhook_razorpay(raw2, rz_sig('WHSEC', raw2)), {'ignored': True}); self.assertIsNone(self.fresh()['plan_until'])
        raw3 = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {'id': 'p', 'order_id': 'order_nope', 'amount': 95000}}}}).encode(); self.assertEqual(self.bl.webhook_razorpay(raw3, rz_sig('WHSEC', raw3)), {'ignored': True})
        raw4 = self.event(o, ev='payment.failed'); self.assertEqual(self.bl.webhook_razorpay(raw4, rz_sig('WHSEC', raw4)), {'ignored': True})
    def test_webhook_off_without_secret(self):
        self.st.razorpay_webhook_secret = ''; raw = b'{}'
        with self.assertRaises(ApiError): self.bl.webhook_razorpay(raw, rz_sig('', raw))
    def test_renewal_stacks_on_remaining_time(self):
        self.bl.admin_grant('a@x.in', 'gold', 100); o = self.order(); self.bl.confirm_checkout(self.fresh(), self.paid_sig(o)); self.assertEqual(self.fresh()['plan_until'], (dt.date.today() + dt.timedelta(days=465)).isoformat())
    def test_mock_provider_needs_dev_mode(self):
        self.st.pay_provider = 'mock'; self.st.dev_mode = True; o = self.bl.create_order(self.fresh(), 'silver', 'monthly'); self.assertEqual(o['provider'], 'mock'); self.bl.mock_confirm(self.fresh(), o['payment_id']); self.assertTrue(self.fresh()['plan_until'])
        self.st.dev_mode = False; self.assertIsNone(self.bl.provider())
        with self.assertRaises(ApiError): self.bl.create_order(self.fresh(), 'silver', 'monthly')
        with self.assertRaises(ApiError): self.bl.mock_confirm(self.fresh(), o['payment_id'])
    def test_not_configured(self):
        self.st.pay_provider = ''
        with self.assertRaises(ApiError) as c: self.order()
        self.assertEqual(c.exception.code, 503)
    # ---- direct UPI
    def test_upi_flow_manual_approval(self):
        s = self.bl.upi_start(self.fresh(), 'gold', 'yearly'); self.assertTrue(s['link'].startswith('upi://pay?')); self.assertIn('pa=dk%40bank', s['link']); self.assertIn('am=950.00', s['link']); self.assertIn('cu=INR', s['link']); self.assertEqual(s['ref'], 'DK%d' % s['payment_id'])
        self.assertEqual(self.bl.upi_start(self.fresh(), 'gold', 'yearly')['payment_id'], s['payment_id'])  # reuses the open one
        s2 = self.bl.upi_start(self.fresh(), 'silver', 'monthly'); self.assertEqual((s2['payment_id'], s2['amount']), (s['payment_id'], '49.00')); self.assertEqual(self.db.one('SELECT tier, period, plan_days, amount_paise FROM payments')['plan_days'], 30)  # same open payment, switched to the new choice
        for bad in ('12345', 'abcdefghijkl', '1234567890123', ''):
            with self.assertRaises(ApiError): self.bl.upi_submit(self.fresh(), s['payment_id'], bad)
        self.bl.upi_submit(self.fresh(), s['payment_id'], '4123 4567 8901'); self.assertIsNone(self.fresh()['plan_until']); self.assertEqual(self.db.one('SELECT status FROM payments')['status'], 'pending_review')  # nothing granted yet
        with self.assertRaises(ApiError): self.bl.upi_submit(self.fresh(), s['payment_id'], '412345678901')  # already submitted
        self.assertEqual(self.bl.admin_list()[0]['status'], 'pending_review'); self.bl.admin_review(s['payment_id'], True); self.assertTrue(self.fresh()['plan_until'])
        with self.assertRaises(ApiError): self.bl.admin_review(s['payment_id'], True)  # cannot approve twice
    def test_upi_utr_cannot_be_reused(self):
        s = self.bl.upi_start(self.fresh(), 'gold', 'yearly'); self.bl.upi_submit(self.fresh(), s['payment_id'], '412345678901'); self.bl.admin_review(s['payment_id'], True)
        u2, _ = register(self.au, email='b@x.in', pan='XYZPD9999Z', mobile='9123456780'); s2 = self.bl.upi_start(u2, 'gold', 'yearly')
        with self.assertRaises(ApiError) as c: self.bl.upi_submit(u2, s2['payment_id'], '412345678901')
        self.assertEqual(c.exception.code, 409)
    def test_upi_reject_tells_the_user(self):
        s = self.bl.upi_start(self.fresh(), 'gold', 'yearly'); self.bl.upi_submit(self.fresh(), s['payment_id'], '412345678901'); self.n.sent.clear(); self.bl.admin_review(s['payment_id'], False, 'not in statement')
        self.assertIsNone(self.fresh()['plan_until']); self.assertTrue([m for m in self.n.sent if 'could not confirm' in (m['subject'] or '')]); self.assertEqual(self.bl.history(self.fresh())[0]['status'], 'rejected')
    def test_cannot_submit_utr_on_another_users_payment(self):
        s = self.bl.upi_start(self.fresh(), 'gold', 'yearly'); u2, _ = register(self.au, email='b@x.in', pan='XYZPD9999Z', mobile='9123456780')
        with self.assertRaises(ApiError) as c: self.bl.upi_submit(u2, s['payment_id'], '412345678901')
        self.assertEqual(c.exception.code, 404)
    def test_upi_off_without_vpa(self):
        self.st.upi_vpa = ''
        with self.assertRaises(ApiError): self.bl.upi_start(self.fresh(), 'gold', 'yearly')
    # ---- receipts, history, grants
    def test_receipt_and_gst_split(self):
        self.st.gst_percent = 18.0; self.st.gstin = '27ABCDE1234F1Z5'; o = self.order(); self.bl.confirm_checkout(self.fresh(), self.paid_sig(o)); pid = self.db.one('SELECT id FROM payments')['id']; r = self.bl.receipt(self.fresh(), pid)
        self.assertEqual((r['amount'], r['taxable'], r['gst']), (950.0, 805.08, 144.92)); self.assertAlmostEqual(r['taxable'] + r['gst'], 950.0); self.assertEqual(r['item'], 'Gold membership (yearly)'); self.assertEqual(r['gstin'], '27ABCDE1234F1Z5')
        u2, _ = register(self.au, email='b@x.in', pan='XYZPD9999Z', mobile='9123456780')
        with self.assertRaises(ApiError): self.bl.receipt(u2, pid)
        self.assertEqual(self.bl.history(self.fresh())[0]['status'], 'paid')
    def test_grant_validation(self):
        with self.assertRaises(ApiError): self.bl.admin_grant('nobody@x.in', 'gold', 30)
        for d in (0, -5, 99999):
            with self.assertRaises(ApiError): self.bl.admin_grant('a@x.in', 'gold', d)
        for t in ('', 'diamond', 'free'):
            with self.assertRaises(ApiError): self.bl.admin_grant('a@x.in', t, 10)
        self.assertEqual(self.bl.admin_grant('a@x.in', 'gold', 10), {'plan_until': (dt.date.today() + dt.timedelta(days=10)).isoformat(), 'tier': 'gold'}); self.assertEqual(self.bl.history(self.fresh())[0]['amount'], 0)
    # ---- tiers, monthly / yearly, switching
    def test_prices_come_from_settings_with_the_yearly_discount(self):
        pi = self.bl.plan_info(); self.assertEqual([t['key'] for t in pi['tiers']], ['silver', 'gold', 'platinum']); g = pi['tiers'][1]
        self.assertEqual((g['monthly'], g['yearly'], g['save_percent'], g['companies'], g['whatsapp']), (99.0, 950.0, 20, 100, True)); self.assertIsNone(pi['tiers'][2]['companies']); self.assertFalse(pi['tiers'][0]['whatsapp'])
        self.st.tiers['silver']['monthly'] = 60.0; o = self.order('silver', 'monthly'); self.assertEqual(o['amount_paise'], 6000)
    def test_yearly_discount_and_explicit_override_in_settings(self):
        import os; os.environ['YEARLY_DISCOUNT_PERCENT'] = '25'; os.environ['SILVER_YEARLY_INR'] = '400'
        try: s2 = Settings()
        finally: del os.environ['YEARLY_DISCOUNT_PERCENT'], os.environ['SILVER_YEARLY_INR']
        self.assertEqual((s2.tiers['silver']['yearly'], s2.tiers['gold']['yearly']), (400.0, float(round(99 * 12 * 0.75))))
    def test_monthly_is_30_days_and_yearly_365(self):
        o = self.order('silver', 'monthly'); self.assertEqual(o['amount_paise'], 4900); self.bl.confirm_checkout(self.fresh(), self.paid_sig(o)); self.assertEqual(self.fresh()['plan_until'], (dt.date.today() + dt.timedelta(days=30)).isoformat()); self.assertEqual(self.fresh()['plan_tier'], 'silver')
        o2 = self.order('silver', 'yearly'); self.bl.confirm_checkout(self.fresh(), self.paid_sig(o2, 'pay_2')); self.assertEqual(self.fresh()['plan_until'], (dt.date.today() + dt.timedelta(days=395)).isoformat())  # same tier: stacks
    def test_unknown_tier_or_period_is_refused_and_creates_nothing(self):
        for t, p in (('free', 'yearly'), ('gold', 'weekly'), ('', ''), (None, 'monthly'), ('GOLD; DROP', 'yearly')):
            with self.assertRaises(ApiError): self.order(t, p)
            with self.assertRaises(ApiError): self.bl.upi_start(self.fresh(), t, p)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM payments')['n'], 0); self.assertEqual(RzMock.log, [])
    def test_switching_tier_converts_the_days_left(self):
        self.bl.admin_grant('a@x.in', 'silver', 30); o = self.order('gold', 'monthly'); self.bl.confirm_checkout(self.fresh(), self.paid_sig(o))  # 30 days of Silver (49/mo) = 14 days of Gold (99/mo), plus 30 new
        self.assertEqual((self.fresh()['plan_tier'], self.fresh()['plan_until']), ('gold', (dt.date.today() + dt.timedelta(days=44)).isoformat()))
        self.assertEqual(self.bl.plan_info(self.fresh())['carry']['silver'], 44 * 99 // 49)  # a downgrade would turn the remaining Gold days into more Silver days
    def test_plan_info_for_a_member_shows_current_plan_and_carry(self):
        self.assertNotIn('current', self.bl.plan_info()); self.bl.admin_grant('a@x.in', 'silver', 98); pi = self.bl.plan_info(self.fresh())
        self.assertEqual((pi['current']['tier'], pi['current']['days_left'], pi['carry']['gold'], pi['carry']['silver']), ('silver', 98, 98 * 49 // 99, 98))
    def test_payments_made_before_tiers_existed_still_render(self):
        self.db.x("INSERT INTO payments(user_id,billed_name,provider,method,amount_paise,status,plan_days,paid_at,created_at,receipt_no) VALUES(?,?,?,?,?,?,?,?,?,?)", (self.u['id'], 'Anita Desai', 'razorpay', 'upi', 29900, 'paid', 365, '2026-01-01', '2026-01-01', 'DKR-2026-000001'))
        pid = self.db.one('SELECT id FROM payments')['id']; self.assertEqual(self.bl.receipt(self.fresh(), pid)['item'], 'Platinum membership'); self.assertEqual(self.bl.history(self.fresh())[0]['item'], 'Platinum membership')

class Mock(BaseHTTPRequestHandler):
    log = []
    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0); Mock.log.append((self.path, dict(self.headers), self.rfile.read(n).decode()))
        b = b'{"ok":true}'; self.send_response(200); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

class Providers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), Mock); threading.Thread(target=cls.srv.serve_forever, daemon=True).start(); cls.base = 'http://127.0.0.1:%d' % cls.srv.server_port
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def setUp(self): Mock.log.clear(); self.st = Settings(); self.st.twilio_base = self.st.msg91_base = self.st.meta_base = self.base
    def test_twilio_sms_and_wa(self):
        st = self.st; st.sms_provider = st.wa_provider = 'twilio'; st.twilio_sid, st.twilio_token, st.twilio_sms_from, st.twilio_wa_from = 'AC1', 'tok', '+1555', 'whatsapp:+1415'; n = Notifier(st)
        self.assertEqual(n.send('sms', '+919876543210', 'hi'), (True, '')); self.assertEqual(n.send('whatsapp', '+919876543210', 'hi'), (True, ''))
        p, h, b = Mock.log[0]; self.assertIn('/Accounts/AC1/Messages.json', p); self.assertTrue(h['Authorization'].startswith('Basic ')); self.assertIn('To=%2B919876543210', b); self.assertIn('whatsapp%3A%2B919876543210', Mock.log[1][2])
    def test_msg91_template_vars(self):
        st = self.st; st.sms_provider = 'msg91'; st.msg91_key = 'K'; st.msg91_otp_template = 'T1'; st.msg91_alert_template = 'T2'; n = Notifier(st)
        self.assertTrue(n.send('sms', '+919876543210', 'x', kind='otp', vars={'otp': '123456'})[0]); j = json.loads(Mock.log[0][2]); self.assertEqual(j['template_id'], 'T1'); self.assertEqual(j['recipients'][0]['otp'], '123456'); self.assertEqual(j['recipients'][0]['mobiles'], '919876543210')
        n.send('sms', '+919876543210', 'x', kind='alert', vars={'name': 'A', 'count': 2, 'amount': '10', 'url': 'u'}); self.assertEqual(json.loads(Mock.log[1][2])['template_id'], 'T2')
    def test_meta_template_and_text(self):
        st = self.st; st.wa_provider = 'meta'; st.meta_token = 'TK'; st.meta_phone_id = '999'; st.meta_alert_template = 'alert_t'; n = Notifier(st)
        n.send('whatsapp', '+919876543210', 'body', kind='alert', vars={'name': 'A', 'count': 1, 'amount': '5', 'url': 'u'}); p, h, b = Mock.log[0]; j = json.loads(b)
        self.assertEqual(p, '/999/messages'); self.assertEqual(h['Authorization'], 'Bearer TK'); self.assertEqual(j['template']['name'], 'alert_t'); self.assertEqual(len(j['template']['components'][0]['parameters']), 4)
        n.send('whatsapp', '+919876543210', 'plain', kind='otp'); self.assertEqual(json.loads(Mock.log[1][2])['type'], 'text')
    def test_failure_is_reported_not_raised(self):
        st = self.st; st.sms_provider = 'twilio'; st.twilio_base = 'http://127.0.0.1:1'; ok, err = Notifier(st).send('sms', '+91', 'x'); self.assertFalse(ok); self.assertTrue(err)
    def test_outbox_retry(self):
        st, db, svc, _ = mk(); svc.n.send = lambda *a, **k: (False, 'boom')
        db.x("INSERT INTO subscribers(name,email,phone,status,token,created_at) VALUES('A B','a@x.in','+911','active','t','2026')"); db.x("INSERT INTO outbox(sub_id,channel,to_addr,kind,body,vars,status,created_at) VALUES(1,'sms','+911','alert','b','{}','pending','x')")
        for _ in range(5): svc.dispatch_outbox()
        self.assertEqual(db.one('SELECT status,tries FROM outbox')['status'], 'failed')




class Live(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st, cls.db, cls.svc, _ = mk(); cls.st.pay_provider = 'mock'; cls.rl = S.RateLimiter()
        cls.srv = S.ThreadingHTTPServer(('127.0.0.1', 0), S.make_handler(cls.svc, cls.st, cls.rl)); threading.Thread(target=cls.srv.serve_forever, daemon=True).start(); cls.b = 'http://127.0.0.1:%d' % cls.srv.server_port
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    seq = [0]
    def setUp(self):
        self.rl.hits.clear(); self.jar = http.cookiejar.CookieJar(); self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar)); self.n = self.svc.n
        Live.seq[0] += 1; k = Live.seq[0]; self.me = dict(email='live%d@x.in' % k, pan='ABCPD%04dZ' % k, mobile='9%09d' % (100000 + k))  # a fresh identity per test: the DB is shared across the class
    def req(self, path, body=None, headers=None, method=None, raw=None):
        h = dict(headers or {}); data = raw
        if body is not None: data = json.dumps(body).encode(); h['Content-Type'] = 'application/json'
        r = urllib.request.Request(self.b + path, data=data, headers=h, method=method)
        try:
            with self.op.open(r) as x: return x.status, x.read(), x.headers
        except urllib.error.HTTPError as e: return e.code, e.read(), e.headers
    def j(self, *a, **k): c, b, h = self.req(*a, **k); return c, json.loads(b)
    def signup(self, **kw): c, j = self.j('/api/auth/signup', payload(**{**self.me, **kw})); self.assertEqual(c, 200, j); return j
    def login(self, email=None, pw='Str0ng-pass!'): return self.j('/api/auth/login', {'email': email or self.me['email'], 'password': pw})
    # ---- site basics
    def test_static_and_headers(self):
        c, b, h = self.req('/'); self.assertEqual(c, 200); self.assertIn(b'DhanKhoj', b); self.assertIn("default-src 'self'", h['Content-Security-Policy']); self.assertEqual(h['X-Content-Type-Options'], 'nosniff')
    def test_path_traversal(self):
        for p in ('/../server.py', '/..%2fserver.py', '/%2e%2e/config.py', '/js/../../.env', '/data/x'): self.assertEqual(self.req(p)[0], 404, p)
    def test_py_and_db_not_served(self):
        for p in ('/server.py', '/auth.py', '/billing.py', '/data/dhankhoj.db'): self.assertEqual(self.req(p)[0], 404, p)
    def test_every_page_loads_and_obeys_csp(self):
        import re
        pages = [f for f in os.listdir(os.path.join(ROOT, 'web')) if f.endswith('.html')]; self.assertGreaterEqual(len(pages), 17)
        for f in pages:
            c, b, h = self.req('/' + f); self.assertEqual(c, 200, f); t = b.decode()
            self.assertFalse(re.search(r'<script(?![^>]*\bsrc=)', t), f + ': inline script'); self.assertFalse(re.search(r'\son\w+\s*=', t), f + ': inline handler')
            for js in re.findall(r'src="(/js/[^"]+)"', t): self.assertEqual(self.req(js)[0], 200, f + ' -> ' + js)
    def test_stats_plan_options(self):
        self.assertGreaterEqual(self.j('/api/stats')[1]['records'], 5); c, p = self.j('/api/plan'); self.assertEqual((p['free_companies'], [t['key'] for t in p['tiers']], p['tiers'][0]['monthly'], p['tiers'][0]['yearly']), (5, ['silver', 'gold', 'platinum'], 49.0, 470.0)); self.assertNotIn('current', p); self.assertIn('Maharashtra', self.j('/api/form-options')[1]['states'])
    def test_check_api(self):
        c, j = self.j('/api/check', {'name': 'Anita Desai', 'pincode': '411001'}); self.assertEqual((c, j['likely']), (200, 1)); self.assertEqual(self.j('/api/check', {'name': 'X'})[0], 400)
    def test_json_required_and_size(self):
        self.assertEqual(self.req('/api/check', raw=b'{}', headers={'Content-Type': 'text/plain'})[0], 415); self.assertEqual(self.req('/api/check', raw=b'x' * 70000, headers={'Content-Type': 'application/json'})[0], 413)
    def test_removed_anonymous_endpoints_are_gone(self):
        for p in ('/api/subscribe', '/api/verify', '/api/resend', '/api/me/update', '/api/unsubscribe'): self.assertEqual(self.j(p, {})[0], 404, p)
        self.assertEqual(self.req('/api/me?t=abc')[0], 404)
    # ---- the whole user journey
    def test_signup_verify_login_dashboard_pay_logout(self):
        self.assertEqual(self.j('/api/dashboard')[0], 401); self.assertEqual(self.j('/api/session')[1]['user'], None)
        r = self.signup(); self.assertNotIn(self.me['pan'], json.dumps(r))
        c, j = self.login(); self.assertEqual(c, 200); self.assertFalse(j['user']['email_verified'])
        c, j = self.j('/api/dashboard'); self.assertEqual((c, j.get('need')), (403, 'verify_email'))
        c, j = self.j('/api/pay/order', {'tier': 'gold', 'period': 'yearly'}); self.assertEqual((c, j.get('need')), (403, 'verify_email'))
        c, j = self.j('/api/auth/verify-email', {'token': r['dev_link'].split('token=')[1]}); self.assertEqual(c, 200)
        c, d = self.j('/api/dashboard'); self.assertEqual(c, 200); self.assertTrue(d['needs_pan']); self.assertEqual((d['likely'], d['plan']['tier']), ([], 'free'))  # signed up, but nothing is searched without a PAN
        c, p = self.j('/api/account/profile', {'pan': 'bad'}); self.assertEqual(c, 400)
        c, p = self.j('/api/account/profile', {'pan': self.me['pan'], 'pincode': '411001', 'folios': ['IN30022822222222']}); self.assertEqual((c, p['pan_masked'], p['pan_set']), (200, 'XXXXXX' + self.me['pan'][-4:], True)); self.assertNotIn(self.me['pan'], json.dumps(p))
        c, d = self.j('/api/dashboard'); self.assertFalse(d['needs_pan']); self.assertEqual({i['company'] for i in d['likely']}, {'Test Co Ltd'}); self.assertFalse(d['plan']['active']); self.assertNotIn(self.me['pan'], json.dumps(d))
        c, j = self.j('/api/account/profile', {'pan': 'ZZZPD9999Z'}); self.assertEqual(c, 403)
        c, j = self.j('/api/account/profile', {'folios': ['AAAA1', 'BBBB2', 'CCCC3', 'DDDD4', 'EEEE5', 'FFFF6']}); self.assertEqual(c, 400)
        self.assertTrue(self.j('/api/session')[1]['user']['email_verified'])
        c, j = self.j('/api/account/channels', {'channels': {'sms': True}}); self.assertEqual((c, j.get('need')), (403, 'upgrade'))  # SMS needs Silver or above
        c, o = self.j('/api/pay/order', {'tier': 'gold', 'period': 'weekly'}); self.assertEqual(c, 400); c, o = self.j('/api/pay/order', {}); self.assertEqual(c, 400)
        c, o = self.j('/api/pay/order', {'tier': 'gold', 'period': 'yearly', 'amount': 1}); self.assertEqual((o['provider'], o['amount_paise']), ('mock', 95000)); self.assertEqual(self.j('/api/pay/mock-confirm', {'payment_id': o['payment_id']})[0], 200)
        c, d = self.j('/api/dashboard'); self.assertEqual((d['plan']['active'], d['plan']['tier']), (True, 'gold'))
        c, j = self.j('/api/account/channels', {'channels': {'sms': True}}); self.assertEqual((c, j.get('need')), (400, 'verify_phone'))
        c, j = self.j('/api/account/phone/send-otp', {}); c2, j2 = self.j('/api/account/phone/verify', {'otp': j['dev_otp']}); self.assertEqual(c2, 200)
        self.assertTrue(self.j('/api/account/channels', {'channels': {'sms': True, 'whatsapp': True}})[1]['channels']['whatsapp'])
        c, h = self.j('/api/account/payments'); self.assertEqual((h['payments'][0]['status'], h['payments'][0]['item']), ('paid', 'Gold membership (yearly)')); c, rc = self.j('/api/pay/receipt?id=%d' % h['payments'][0]['id']); self.assertEqual(c, 200)
        c, pl = self.j('/api/plan'); self.assertEqual((pl['current']['tier'], pl['current']['active']), ('gold', True))
        self.assertEqual(self.j('/api/auth/logout', {})[0], 200); self.assertEqual(self.j('/api/dashboard')[0], 401)
    def test_cookie_flags_and_secure_variant(self):
        self.signup(); c, b, h = self.req('/api/auth/login', {'email': self.me['email'], 'password': 'Str0ng-pass!'}); ck = h['Set-Cookie']; self.assertIn('dk_session=', ck); self.assertIn('HttpOnly', ck); self.assertIn('SameSite=Lax', ck); self.assertNotIn('Secure', ck)
        st2 = Settings(); st2.base_url = 'https://x.in'; st2.secure_cookies = True; st2.dev_mode = True; st2.salt = 's'; st2.email_provider = st2.sms_provider = st2.wa_provider = 'console'; db2 = DB(':memory:'); svc2 = Service(db2, st2, Notifier(st2)); a2 = Auth(svc2); register(a2)
        srv = S.ThreadingHTTPServer(('127.0.0.1', 0), S.make_handler(svc2, st2, S.RateLimiter())); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            r = urllib.request.Request('http://127.0.0.1:%d/api/auth/login' % srv.server_port, json.dumps({'email': 'a@x.in', 'password': 'Str0ng-pass!'}).encode(), {'Content-Type': 'application/json'})
            with urllib.request.urlopen(r) as x: ck = x.headers['Set-Cookie']; self.assertTrue(ck.startswith('__Host-dk=')); self.assertIn('Secure', ck); self.assertIn('Strict-Transport-Security', x.headers)
        finally: srv.shutdown()
    def test_cross_site_post_is_blocked(self):
        c, j = self.j('/api/auth/login', {'email': 'a@x.in', 'password': 'x'}, headers={'Origin': 'http://evil.example'}); self.assertEqual(c, 403)
        c, j = self.j('/api/auth/login', {'email': 'a@x.in', 'password': 'x'}, headers={'Origin': self.b}); self.assertEqual(c, 401)
    def test_tampered_or_foreign_cookie_is_anonymous(self):
        self.signup(); self.login(); c, b, h = self.req('/api/dashboard', headers={'Cookie': 'dk_session=forged'}); self.assertIn(c, (401, 403)); self.assertEqual(self.req('/api/session', headers={'Cookie': 'dk_session=forged'})[0], 200)
    def test_password_reset_over_http(self):
        self.signup(email='r@x.in', pan='RRRPD1111R', mobile='9222233333'); c, j = self.j('/api/auth/forgot', {'email': 'r@x.in'}); t = j['dev_link'].split('token=')[1]
        self.assertTrue(self.j('/api/auth/reset-check', {'token': t})[1]['valid']); self.assertFalse(self.j('/api/auth/reset-check', {'token': 'x'})[1]['valid'])
        self.assertEqual(self.j('/api/auth/reset', {'token': t, 'password': 'Brand-New-Pass-5'})[0], 200); self.assertEqual(self.j('/api/auth/reset', {'token': t, 'password': 'Another-Pass-77'})[0], 410); self.assertEqual(self.login('r@x.in', 'Brand-New-Pass-5')[0], 200)
    def test_unsubscribe_page_api(self):
        self.signup(email='u@x.in', pan='UUUPD1111U', mobile='9333344444'); tok = self.db.one("SELECT token FROM subscribers WHERE email='u@x.in'")['token']
        c, j = self.j('/api/unsub/info', {'t': tok}); self.assertTrue(j['channels']['email']); c, j = self.j('/api/unsub/set', {'t': tok, 'what': 'email'}); self.assertFalse(j['channels']['email']); self.assertEqual(self.j('/api/unsub/info', {'t': 'bad'})[0], 404)
    def test_delete_account_over_http(self):
        self.signup(email='d@x.in', pan='DDDPD1111D', mobile='9444455555'); self.login('d@x.in'); self.assertEqual(self.j('/api/account/delete', {'password': 'nope'})[0], 403)
        self.assertEqual(self.j('/api/account/delete', {'password': 'Str0ng-pass!'})[0], 200); self.assertEqual(self.login('d@x.in')[0], 401); self.assertIsNone(self.db.one("SELECT 1 FROM subscribers WHERE email='d@x.in'"))
    # ---- limits
    def test_rate_limits(self):
        codes = [self.j('/api/auth/signup', payload(consent=False, email='r%d@x.in' % i))[0] for i in range(12)]; self.assertIn(429, codes)
        self.rl.hits.clear(); codes = [self.login('nobody@x.in', 'x' * 9)[0] for _ in range(12)]; self.assertIn(429, codes)
    def test_no_dev_links_in_production_mode(self):
        self.st.dev_mode = False
        try:
            c, j = self.j('/api/auth/signup', payload(email='prod@x.in', pan='PPPPD1111P', mobile='9555566666')); self.assertEqual(c, 200); self.assertNotIn('dev_link', j)
            c, j = self.j('/api/auth/forgot', {'email': 'prod@x.in'}); self.assertNotIn('dev_link', j); self.assertEqual(self.j('/api/pay/mock-confirm', {'payment_id': 1})[0], 401)
        finally: self.st.dev_mode = True
    # ---- admin + payments
    def test_admin_auth(self):
        for p in ('/api/admin/stats', '/api/admin/payments', '/api/admin/claims'): self.assertEqual(self.req(p)[0], 403, p); self.assertEqual(self.req(p, headers={'X-Admin-Token': 'bad'})[0], 403)
        for p in ('/api/admin/payment/review', '/api/admin/grant'): self.assertEqual(self.j(p, {})[0], 403, p)
        c, j = self.j('/api/admin/stats', headers={'X-Admin-Token': 'adm'}); self.assertEqual(c, 200); self.assertIn('revenue_inr', j)
    def test_admin_upi_approval_over_http(self):
        self.st.upi_vpa = 'dk@bank'
        try:
            self.signup(email='p@x.in', pan='PAYPD1111P', mobile='9666677777'); t = self.n.sent and None
            link = [m for m in self.n.sent if m['to'] == 'p@x.in' and 'verify-email' in m['body']][-1]['body'].split('token=')[1].split()[0]; self.j('/api/auth/verify-email', {'token': link}); self.login('p@x.in')
            c, s = self.j('/api/pay/upi/start', {'tier': 'platinum', 'period': 'monthly'}); self.assertEqual((c, s['amount']), (200, '199.00')); self.assertEqual(self.j('/api/pay/upi/submit', {'payment_id': s['payment_id'], 'utr': '412345678901'})[0], 200)
            H = {'X-Admin-Token': 'adm'}; c, pl = self.j('/api/admin/payments', headers=H); row = [p for p in pl['payments'] if p['id'] == s['payment_id']][0]; self.assertEqual((row['status'], row['utr']), ('pending_review', '412345678901'))
            self.assertFalse(self.j('/api/session')[1]['user']['plan']['active']); self.assertEqual(self.j('/api/admin/payment/review', {'id': s['payment_id'], 'approve': True}, headers=H)[0], 200); self.assertTrue(self.j('/api/session')[1]['user']['plan']['active'])
            c, g = self.j('/api/admin/grant', {'email': 'p@x.in', 'tier': 'gold', 'days': 5, 'note': 'x'}, headers=H); self.assertEqual((c, g['tier']), (200, 'gold'))
        finally: self.st.upi_vpa = ''
    def test_razorpay_webhook_over_http_and_csp(self):
        st = self.st; old = (st.pay_provider, st.razorpay_key_id, st.razorpay_key_secret, st.razorpay_webhook_secret); st.pay_provider, st.razorpay_key_id, st.razorpay_key_secret, st.razorpay_webhook_secret = 'razorpay', 'k', 's', 'wh'
        try:
            c, b, h = self.req('/upgrade.html'); self.assertIn('https://checkout.razorpay.com', h['Content-Security-Policy']); self.assertIn('frame-src https://api.razorpay.com', h['Content-Security-Policy'])
            self.assertNotIn('razorpay', self.req('/')[2]['Content-Security-Policy']); self.assertNotIn('razorpay', self.req('/dashboard.html')[2]['Content-Security-Policy'])
            raw = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {'id': 'p', 'order_id': 'order_x', 'amount': 1}}}}).encode()
            self.assertEqual(self.req('/api/webhook/razorpay', raw=raw, headers={'Content-Type': 'application/json', 'X-Razorpay-Signature': 'bad'})[0], 400)
            c, j = self.j('/api/webhook/razorpay', raw=raw, headers={'Content-Type': 'application/json', 'X-Razorpay-Signature': rz_sig('wh', raw), 'Origin': 'http://razorpay.example'}); self.assertEqual((c, j['ok']), (200, True))  # no cookies / origin check for server-to-server
        finally: st.pay_provider, st.razorpay_key_id, st.razorpay_key_secret, st.razorpay_webhook_secret = old
    def test_admin_ingest_upload(self):
        c, j = self.j('/api/admin/ingest?company=Up+Co&filename=a.txt&declared=2026-10-01', raw=b'INT DIV 2026-27 IN30055 PRIYA NAIR KOCHI 682001 20 85.00\n', headers={'X-Admin-Token': 'adm', 'Content-Type': 'application/octet-stream'}); self.assertEqual(j['rows'], 1)
        c, j = self.j('/api/admin/ingest?company=X&filename=a.exe', raw=b'abc', headers={'X-Admin-Token': 'adm'}); self.assertEqual(c, 400); self.assertEqual(self.req('/api/admin/ingest?company=X&filename=a.txt', raw=b'abc')[0], 403)


class GMock(BaseHTTPRequestHandler):
    users = {}
    def log_message(self, *a): pass
    def do_POST(self):
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
        ok = form.get('client_secret') == ['sec'] and form.get('code', [''])[0] in GMock.users
        b = json.dumps({'access_token': 'at-' + form['code'][0]} if ok else {'error': 'invalid_grant'}).encode()
        self.send_response(200 if ok else 400); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        info = GMock.users.get(self.headers.get('Authorization', '')[10:])
        b = json.dumps(info or {}).encode(); self.send_response(200 if info else 401); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)


class GoogleFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gs = ThreadingHTTPServer(('127.0.0.1', 0), GMock); threading.Thread(target=cls.gs.serve_forever, daemon=True).start(); g = 'http://127.0.0.1:%d' % cls.gs.server_port
        cls.st, cls.db, cls.svc, _ = mk(); cls.rl = S.RateLimiter()
        cls.srv = S.ThreadingHTTPServer(('127.0.0.1', 0), S.make_handler(cls.svc, cls.st, cls.rl)); threading.Thread(target=cls.srv.serve_forever, daemon=True).start(); cls.port = cls.srv.server_port
        cls.st.google_auth_url, cls.st.google_token_url, cls.st.google_userinfo_url = g + '/auth', g + '/token', g + '/userinfo'
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown(); cls.gs.shutdown()
    def setUp(self): self.rl.hits.clear(); self.st.google_client_id, self.st.google_client_secret = 'cid', 'sec'; GMock.users.clear()
    def call(self, path, cookie=''):
        import http.client
        c = http.client.HTTPConnection('127.0.0.1', self.port); c.request('GET', path, headers={'Cookie': cookie} if cookie else {}); r = c.getresponse(); body = r.read(); return r.status, r, body
    def start(self, nxt='/dashboard.html'):
        c, r, _ = self.call('/auth/google/start?next=' + urllib.parse.quote(nxt)); self.assertEqual(c, 302)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(r.getheader('Location')).query); ck = r.getheader('Set-Cookie').split(';')[0]
        return q['state'][0], ck
    def finish(self, code, info, nxt='/dashboard.html', state=None, ck=None):
        GMock.users[code] = info; st, c2 = self.start(nxt)
        c, r, _ = self.call('/auth/google/callback?code=%s&state=%s' % (code, state or st), ck or c2); return c, r
    def sess(self, r):
        for h in r.headers.get_all('Set-Cookie') or []:
            if h.startswith('dk_session'):
                v = h.split(';')[0]
                if not v.endswith('='): return v
        return ''
    def me(self, ck):
        c, r, b = self.call('/api/session', ck); return json.loads(b)['user']
    G = lambda self, n, **kw: {'sub': 'g-' + n, 'email': n + '@gmail.com', 'email_verified': True, 'given_name': n.title(), 'family_name': 'Kumar', **kw}
    def test_options_and_off(self):
        self.assertTrue(json.loads(self.call('/api/auth/options')[2])['google'])
        self.st.google_client_id = ''
        self.assertFalse(json.loads(self.call('/api/auth/options')[2])['google'])
        c, r, _ = self.call('/auth/google/start'); self.assertEqual((c, r.getheader('Location')), (302, '/signin.html?gerr=off'))
    def test_start_redirect(self):
        c, r, _ = self.call('/auth/google/start?next=/upgrade.html%3Fplan%3Dgold'); loc = r.getheader('Location'); q = urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query)
        self.assertEqual((q['client_id'], q['response_type'], q['scope']), (['cid'], ['code'], ['openid email profile'])); self.assertIn('/callback', q['redirect_uri'][0]); self.assertIn('HttpOnly', r.getheader('Set-Cookie'))
    def test_new_account(self):
        c, r = self.finish('c1', self.G('asha'), '/upgrade.html?plan=gold&go=1'); self.assertEqual((c, r.getheader('Location')), (302, '/upgrade.html?plan=gold&go=1'))
        ck = self.sess(r); self.assertTrue(ck); u = self.me(ck); self.assertTrue(u['email_verified']); self.assertEqual(u['first_name'], 'Asha')
        row = self.db.one('SELECT * FROM subscribers WHERE email=?', ('asha@gmail.com',)); self.assertEqual((row['status'], row['phone'], row['google_sub']), ('active', '', 'g-asha'))
        self.assertTrue(self.db.one("SELECT 1 FROM consents WHERE user_id=? AND subject='terms' AND source='google'", (row['id'],)))
        c, r, b = self.call('/api/account/profile', ck); p = json.loads(b); self.assertEqual(p['mobile'], '')
    def test_second_login_same_user_and_no_mobile_clash(self):
        self.finish('c2', self.G('ravi')); self.finish('c3', self.G('ravi')); self.assertEqual(self.db.one('SELECT COUNT(*) n FROM subscribers WHERE email=?', ('ravi@gmail.com',))['n'], 1)
        c, r = self.finish('c4', self.G('meena')); self.assertEqual(c, 302); self.assertTrue(self.sess(r))  # two accounts without a mobile number are fine
    def test_links_to_verified_password_account(self):
        st, db, svc, au, bl, cl = self.st, self.db, self.svc, Auth(self.svc), None, None
        u, _ = register(au, email='kiran@gmail.com'); c, r = self.finish('c5', self.G('kiran')); self.assertTrue(self.sess(r))
        self.assertEqual(db.one('SELECT google_sub FROM subscribers WHERE id=?', (u['id'],))['google_sub'], 'g-kiran'); self.assertEqual(au.login('kiran@gmail.com', 'Str0ng-pass!')[1]['id'], u['id'])
    def test_unverified_password_account_is_taken_over_safely(self):
        au = Auth(self.svc); au.signup(payload(email='dev@gmail.com', mobile='9811111111')); u = au._by_email('dev@gmail.com'); self.assertIsNone(u['email_verified_at'])
        c, r = self.finish('c6', self.G('dev')); self.assertTrue(self.sess(r))
        with self.assertRaises(ApiError): au.login('dev@gmail.com', 'Str0ng-pass!')  # the squatter's password no longer works
        self.assertTrue(au._get(u['id'])['email_verified_at'])
    def test_rejections(self):
        c, r = self.finish('c7', self.G('bad', email_verified=False)); self.assertEqual(r.getheader('Location'), '/signin.html?gerr=unverified'); self.assertFalse(self.sess(r))
        self.assertIsNone(self.db.one('SELECT 1 FROM subscribers WHERE email=?', ('bad@gmail.com',)))
        st, ck = self.start(); GMock.users['c8'] = self.G('x1')
        c, r, _ = self.call('/auth/google/callback?code=c8&state=WRONG', ck); self.assertEqual(r.getheader('Location'), '/signin.html?gerr=state')
        c, r, _ = self.call('/auth/google/callback?code=c8&state=' + st); self.assertEqual(r.getheader('Location'), '/signin.html?gerr=state')  # no cookie
        c, r, _ = self.call('/auth/google/callback?error=access_denied&state=' + st, ck); self.assertEqual(r.getheader('Location'), '/signin.html?gerr=cancelled')
        c, r, _ = self.call('/auth/google/callback?code=nope&state=' + st, ck); self.assertEqual(r.getheader('Location'), '/signin.html?gerr=failed'); self.assertFalse(self.sess(r))
    def test_open_redirect_blocked(self):
        for bad in ('//evil.com', 'https://evil.com', '/a b', 'javascript:alert(1)'):
            c, r = self.finish('c9', self.G('nx'), bad); self.assertEqual(r.getheader('Location'), '/dashboard.html', bad)


class Wsgi(unittest.TestCase):
    """passenger_wsgi.py lets Hostinger / cPanel / gunicorn run the same site."""
    @classmethod
    def setUpClass(cls):
        import tempfile, importlib
        cls.tmp = tempfile.mkdtemp(); os.environ['DB_PATH'] = os.path.join(cls.tmp, 'w.db'); os.environ['BASE_URL'] = 'http://t'
        sys.path.insert(0, ROOT); cls.w = importlib.import_module('passenger_wsgi')
    def call(self, method='GET', path='/', body=b'', ctype=''):
        from wsgiref.util import setup_testing_defaults
        e = {'REQUEST_METHOD': method, 'REQUEST_URI': path, 'PATH_INFO': path.split('?')[0], 'QUERY_STRING': path.partition('?')[2], 'wsgi.input': io.BytesIO(body), 'CONTENT_LENGTH': str(len(body)), 'CONTENT_TYPE': ctype, 'HTTP_HOST': 't', 'HTTP_ORIGIN': 'http://t'}
        setup_testing_defaults(e); got = {}
        def sr(status, headers): got['s'], got['h'] = status, dict(headers)
        b = b''.join(self.w.application(e, sr)); return got['s'], got['h'], b
    def test_home_page_served_from_root(self):
        s, h, b = self.call('GET', '/'); self.assertTrue(s.startswith('200'), s); self.assertIn(b'DhanKhoj', b); self.assertIn('text/html', h['Content-Type']); self.assertIn("default-src 'self'", h['Content-Security-Policy'])
    def test_assets_and_api(self):
        self.assertTrue(self.call('GET', '/css/site.css')[0].startswith('200')); self.assertTrue(self.call('GET', '/fonts/dmsans.woff')[0].startswith('200'))
        s, h, b = self.call('GET', '/api/plan'); self.assertTrue(s.startswith('200')); self.assertEqual([t['key'] for t in json.loads(b)['tiers']], ['silver', 'gold', 'platinum'])
    def test_post_and_cookie(self):
        s, h, b = self.call('POST', '/api/auth/login', json.dumps({'email': 'no@x.in', 'password': 'x'}).encode(), 'application/json'); self.assertTrue(s.startswith('401'), s); self.assertFalse(json.loads(b)['ok'])
    def test_traversal_and_404(self):
        self.assertTrue(self.call('GET', '/../config.py')[0].startswith('404')); self.assertTrue(self.call('GET', '/nope.html')[0].startswith('404'))


import registry, crawler

NSE_CSV = "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\nREC,REC Limited,EQ,01-01-2008,10,1,INE020B01018,10\nTCS,Tata Consultancy Services Limited,EQ,01-01-2004,1,1,INE467B01029,1\n"
BSE_CSV = "Security Code,Security Id,Issuer Name,Security Name,ISIN No\n532955,REC,REC LIMITED,REC LTD,INE020B01018\n500400,TATAPOWER,Tata Power Company Limited,TATA POWER,INE245A01021\n999999,BAD,Broken Co,BROKEN,XX123\n"


class Registry(unittest.TestCase):
    def setUp(self): self.db = DB(':memory:')
    def test_nse_bse_merge_on_isin(self):
        a = registry.import_master(self.db, NSE_CSV, is_text=True); b = registry.import_master(self.db, BSE_CSV, is_text=True)
        self.assertEqual(a['new'], 2); self.assertEqual(b['merged'], 1); self.assertEqual(b['bad_isin'], 1)
        r = self.db.one("SELECT * FROM companies WHERE isin='INE020B01018'"); self.assertEqual((r['nse_symbol'], r['bse_code']), ('REC', '532955'))
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM companies')['n'], 4)  # REC, TCS, Tata Power, Broken Co
    def test_reimport_is_idempotent(self):
        registry.import_master(self.db, NSE_CSV, is_text=True); r = registry.import_master(self.db, NSE_CSV, is_text=True)
        self.assertEqual((r['new'], r['merged'], r['same']), (0, 0, 2))
    def test_canonical_keys(self):
        self.assertEqual(registry.dp_key('IN300118-11111111'), 'IN30011811111111'); self.assertEqual(registry.dp_key('1201 0900 0001 2345'), '1201090000012345')
        self.assertEqual(registry.dp_key('123456'), ''); self.assertEqual(registry.find_dp_keys('folio 1201090000012345 / IN300118 11111111'), {'1201090000012345', 'IN30011811111111'})
        self.assertEqual(registry.norm_cin('L40101DL1969GOI005069'), 'L40101DL1969GOI005069'); self.assertEqual(registry.norm_cin('nonsense'), '')
    def test_name_only_join_without_isin(self):
        registry.upsert_company(self.db, 'Acme Industries Limited'); _, how = registry.upsert_company(self.db, 'ACME INDUSTRIES LTD', isin='INE000A01010')
        self.assertEqual(how, 'merged'); self.assertEqual(self.db.one('SELECT COUNT(*) n FROM companies')['n'], 1)


class Keys(unittest.TestCase):
    def setUp(self): self.st, self.db, self.svc, _ = mk()
    def test_dp_key_stored_and_matched(self):
        r = self.db.one("SELECT dp_key FROM records WHERE folio='IN30011811111111'"); self.assertEqual(r['dp_key'], 'IN30011811111111')
        res = M.find_matches(self.db, 'Totally Different Name', folios=['IN300118-11111111'], with_reason=True)
        self.assertEqual((res[0][1], res[0][3]), ('high', 'dp_client_id'))
    def test_name_only_single_word_never_alerts(self):
        for r in M.find_matches(self.db, 'Ramesh'): self.assertEqual(r[1], 'low')
    def test_stated_total_validation(self):
        txt = LINES.replace('Test', 'Test') + "\nTOTAL 1,211.25\n"
        _, db, _, res = mk(text=txt, company='Total Co'); self.assertEqual(res['stated_total'], 1211.25); self.assertEqual(res['validation'], 'ok')
        _, db, _, res = mk(text=LINES + "\nTOTAL 5,000.00\n", company='Short Co'); self.assertEqual(res['validation'], 'partial')
        self.assertEqual(db.one('SELECT validation FROM lists')['validation'], 'partial')
        _, db, _, res = mk(); self.assertEqual(res['validation'], 'unverified')
    def test_father_name_lifts_confidence(self):
        csvt = "FOLIO,NAME,FATHER NAME,ADD1,PINCODE,HOLDING,NET DIVIDEND\n7001,SUNIL SHARMA,RAJESH SHARMA,PUNE,411001,10,100.00\n"
        d = tempfile.mkdtemp(); p = os.path.join(d, 'f.csv'); _w(p, csvt); db = DB(':memory:'); ingest.ingest_file(db, 'Fa Co', p, declared_on='2026-11-14')
        no = M.find_matches(db, 'Sunil Sharma', pincode='', with_reason=True); yes = M.find_matches(db, 'Sunil Sharma', pincode='', father='Rajesh Sharma', with_reason=True)
        self.assertEqual(no[0][1], 'medium'); self.assertEqual(yes[0][1], 'high'); self.assertIn('father', yes[0][3])


class _Site(BaseHTTPRequestHandler):
    hits = []
    def log_message(self, *a): pass
    def do_GET(self):
        _Site.hits.append(self.path)
        if self.path == '/robots.txt':
            return self._send(200, b'User-agent: *\nDisallow: /private/\n', 'text/plain')
        if self.path == '/investors':
            return self._send(200, b'<html><a href="/files/unpaid-dividend-2026-27.txt">Unpaid Dividend FY 2026-27</a><a href="/files/annual-report.pdf">Annual report</a><a href="/private/unclaimed-dividend.txt">Unclaimed hidden</a></html>', 'text/html')
        if self.path == '/files/unpaid-dividend-2026-27.txt':
            return self._send(200, LINES.encode() + b'\nTOTAL 1211.25\n', 'text/plain')
        self._send(404, b'no', 'text/plain')
    def _send(self, code, body, ct):
        self.send_response(code); self.send_header('Content-Type', ct); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)


class Crawl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), _Site); cls.port = cls.srv.server_address[1]; threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        crawler.HOST_DELAY = 0; crawler._robots.clear()
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def setUp(self):
        self.db = DB(':memory:'); self.dir = tempfile.mkdtemp(); _Site.hits.clear(); crawler._robots.clear()
        self.cid, _ = registry.upsert_company(self.db, 'Mock Power Ltd'); self.base = 'http://127.0.0.1:%d' % self.port
    def run_all(self):
        self.db.x('UPDATE crawl_targets SET next_check=0'); return crawler.crawl_due(self.db, self.dir)
    def test_link_extraction_filters(self):
        links = crawler.extract_links('http://h/investors', '<a href="/a/unpaid-dividend.pdf">Unpaid dividend</a><a href="/a/annual.pdf">Annual</a><a href="mailto:x@y">m</a>')
        self.assertEqual([u for u, _ in links], ['http://h/a/unpaid-dividend.pdf'])
    def test_crawl_discovers_ingests_and_records_provenance(self):
        registry.add_crawl_target(self.db, self.cid, self.base + '/investors'); r = self.run_all()
        self.assertEqual((r[0]['docs'], r[0]['parsed']), (1, 1))
        sd = self.db.one('SELECT * FROM source_docs'); self.assertEqual((sd['status'], sd['rows_parsed'], sd['validation']), ('parsed', 5, 'ok')); self.assertTrue(sd['url'].endswith('2026-27.txt')); self.assertEqual(len(sd['content_hash']), 64)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM records')['n'], 5); self.assertEqual(self.db.one('SELECT fy FROM lists')['fy'], '2026-27')
        self.assertNotIn('/files/annual-report.pdf', _Site.hits)  # irrelevant files are not downloaded
        self.assertNotIn('/private/unclaimed-dividend.txt', _Site.hits)  # robots.txt respected
    def test_second_run_detects_no_change(self):
        registry.add_crawl_target(self.db, self.cid, self.base + '/investors'); self.run_all(); n = len(_Site.hits)
        r = self.run_all(); self.assertEqual(r[0]['status'], 'unchanged'); self.assertEqual(self.db.one('SELECT COUNT(*) n FROM lists')['n'], 1)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM records')['n'], 5)
    def test_robots_block_and_failure_backoff(self):
        registry.add_crawl_target(self.db, self.cid, self.base + '/private/x'); r = self.run_all(); self.assertEqual(r[0]['status'], 'error'); self.assertIn('robots', r[0]['error'])
        t = self.db.one('SELECT * FROM crawl_targets'); self.assertEqual(t['fails'], 1); self.assertGreater(t['next_check'], time.time() + 3600)
    def test_missing_page_is_error_not_crash(self):
        registry.add_crawl_target(self.db, self.cid, self.base + '/missing'); self.assertEqual(self.run_all()[0]['status'], 'error')
    def test_rejects_non_http_target(self): self.assertIsNone(registry.add_crawl_target(self.db, self.cid, 'file:///etc/passwd'))


class Coverage(unittest.TestCase):
    def setUp(self): self.st, self.db, self.svc, _ = mk(); registry.import_master(self.db, NSE_CSV, is_text=True)
    def test_coverage_lists_covered_and_not_yet(self):
        c = self.svc.coverage(); st = {x['name']: x['state'] for x in c['companies']}
        self.assertEqual(st['Test Co Ltd'], 'covered'); self.assertEqual(st['REC Limited'], 'not_yet'); self.assertEqual(c['companies'][0]['state'], 'covered')
        self.assertTrue(any('iepf' in o['url'] for o in c['official']))
    def test_coverage_search_by_symbol_and_isin(self):
        self.assertEqual([x['name'] for x in self.svc.coverage('REC')['companies']], ['REC Limited']); self.assertEqual(len(self.svc.coverage('INE467B01029')['companies']), 1)
    def test_admin_stats_has_registry(self): self.assertEqual(self.svc.admin_stats()['registry']['with_isin'], 2)


class SkipVerify(unittest.TestCase):
    def test_skip_email_verify_only_in_dev_mode(self):
        st, db, svc, au, *_ = stack(dev_mode=True, skip_email_verify=True); r = au.signup(payload()); self.assertTrue(r['verified']); self.assertTrue(au._by_email('a@x.in')['email_verified_at'])
        tok, u = au.login('a@x.in', 'Str0ng-pass!'); self.assertTrue(tok)
    def test_normal_signup_still_needs_email_link(self):
        st, db, svc, au, *_ = stack(); r = au.signup(payload()); self.assertNotIn('verified', r); self.assertIsNone(au._by_email('a@x.in')['email_verified_at'])
    def test_flag_ignored_without_dev_mode(self):
        os.environ['SKIP_EMAIL_VERIFY'] = '1'; os.environ.pop('DEV_MODE', None)
        try: self.assertFalse(Settings().skip_email_verify)
        finally: os.environ.pop('SKIP_EMAIL_VERIFY')


class PanMessages(unittest.TestCase):
    def msg(self, v):
        from auth import clean_pan
        with self.assertRaises(ApiError) as c: clean_pan(v)
        return c.exception.msg
    def test_specific_errors(self):
        self.assertIn('exactly 10', self.msg('ABCDE123F')); self.assertIn('4th letter', self.msg('ABCDE1234F')); self.assertIn('5 letters', self.msg('1234567890'))
    def test_valid(self):
        from auth import clean_pan; self.assertEqual(clean_pan(' abcpe1234f '), 'ABCPE1234F')


class IdleSession(unittest.TestCase):
    def setUp(self): self.st, self.db, self.svc, self.au, *_ = stack(); self.u, _ = register(self.au)
    def test_active_session_stays_and_idle_one_ends(self):
        tok, u = self.au.login('a@x.in', 'Str0ng-pass!'); self.assertTrue(self.au.user_for(tok))
        self.db.x('UPDATE sessions SET last_seen=?', (time.time() - 3 * 60,)); self.assertTrue(self.au.user_for(tok))  # 3 min idle: still in (limit is 5)
        self.db.x('UPDATE sessions SET last_seen=?', (time.time() - 7 * 60,)); self.assertIsNone(self.au.user_for(tok))
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM sessions')['n'], 0)
    def test_activity_refreshes_last_seen(self):
        tok, u = self.au.login('a@x.in', 'Str0ng-pass!'); self.db.x('UPDATE sessions SET last_seen=?', (time.time() - 4 * 60,)); self.au.user_for(tok)
        self.assertGreater(self.db.one('SELECT last_seen FROM sessions')['last_seen'], time.time() - 5)
    def test_idle_limit_zero_means_never(self):
        self.st.session_idle_min = 0; tok, u = self.au.login('a@x.in', 'Str0ng-pass!'); self.db.x('UPDATE sessions SET last_seen=?', (time.time() - 86400,)); self.assertTrue(self.au.user_for(tok))


if __name__ == '__main__':
    unittest.main(verbosity=1)
