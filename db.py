import os
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, symbol TEXT, isin TEXT, website TEXT);
CREATE TABLE IF NOT EXISTS lists(
  id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, fy TEXT, dtype TEXT, source_url TEXT,
  declared_on TEXT, iepf_due TEXT, n_rows INTEGER DEFAULT 0, total REAL DEFAULT 0,
  ingested_at TEXT, file_hash TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS records(
  id INTEGER PRIMARY KEY, list_id INTEGER NOT NULL, company_id INTEGER NOT NULL,
  folio TEXT, folio_key TEXT, blob TEXT, pincode TEXT, holding INTEGER, amount REAL, rowhash TEXT UNIQUE);
CREATE INDEX IF NOT EXISTS idx_rec_folio ON records(folio_key);
CREATE INDEX IF NOT EXISTS idx_rec_list ON records(list_id);
CREATE TABLE IF NOT EXISTS rec_tok(token TEXT NOT NULL, rec_id INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tok ON rec_tok(token);
CREATE TABLE IF NOT EXISTS subscribers(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, aliases TEXT DEFAULT '[]', email TEXT NOT NULL, phone TEXT NOT NULL,
  pincode TEXT, folios TEXT DEFAULT '[]', ch_email INTEGER DEFAULT 1, ch_sms INTEGER DEFAULT 1, ch_wa INTEGER DEFAULT 0,
  status TEXT DEFAULT 'pending', token TEXT UNIQUE, otp_email TEXT, otp_phone TEXT, otp_exp REAL, otp_tries INTEGER DEFAULT 0,
  otp_sent_at REAL DEFAULT 0, consent_at TEXT, created_at TEXT, verified_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sub_unique ON subscribers(email, name);
CREATE TABLE IF NOT EXISTS matches(
  id INTEGER PRIMARY KEY, sub_id INTEGER NOT NULL, rec_id INTEGER NOT NULL, conf TEXT, score REAL,
  first_seen TEXT, notified INTEGER DEFAULT 0, UNIQUE(sub_id, rec_id));
CREATE TABLE IF NOT EXISTS reminders(sub_id INTEGER, rec_id INTEGER, stage INTEGER, sent_at TEXT, PRIMARY KEY(sub_id, rec_id, stage));
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY, sub_id INTEGER, channel TEXT, to_addr TEXT, kind TEXT, subject TEXT, body TEXT, vars TEXT,
  status TEXT DEFAULT 'pending', err TEXT, tries INTEGER DEFAULT 0, created_at TEXT, sent_at TEXT);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS source_docs(
  id INTEGER PRIMARY KEY, company_id INTEGER, url TEXT, fetched_at TEXT, content_hash TEXT, bytes INTEGER, kind TEXT,
  status TEXT, rows_parsed INTEGER DEFAULT 0, rows_skipped INTEGER DEFAULT 0, parsed_total REAL, stated_total REAL, validation TEXT, report TEXT, list_id INTEGER);
CREATE INDEX IF NOT EXISTS idx_src_company ON source_docs(company_id);
CREATE TABLE IF NOT EXISTS crawl_targets(
  id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, url TEXT NOT NULL UNIQUE, kind TEXT DEFAULT 'page', active INTEGER DEFAULT 1,
  last_checked TEXT, last_hash TEXT, last_status TEXT, last_error TEXT, fails INTEGER DEFAULT 0, next_check REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS experts(
  id INTEGER PRIMARY KEY, name TEXT, profession TEXT, membership_no TEXT, city TEXT, email TEXT UNIQUE, phone TEXT, languages TEXT,
  status TEXT DEFAULT 'pending', admin_note TEXT, consent_at TEXT, created_at TEXT, verified_at TEXT);
CREATE TABLE IF NOT EXISTS claim_requests(
  id INTEGER PRIMARY KEY, sub_id INTEGER, items TEXT, notes TEXT, status TEXT DEFAULT 'new', expert_id INTEGER,
  quote_amount REAL, quote_note TEXT, consent_at TEXT, created_at TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS idx_claim_sub ON claim_requests(sub_id);
CREATE TABLE IF NOT EXISTS sessions(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, token_hash TEXT NOT NULL UNIQUE, created_at REAL, expires_at REAL, ip TEXT);
CREATE INDEX IF NOT EXISTS idx_sess_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS auth_tokens(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, exp REAL, used_at REAL, created_at REAL);
CREATE INDEX IF NOT EXISTS idx_tok_user ON auth_tokens(user_id, kind);
CREATE TABLE IF NOT EXISTS unlocks(
  user_id INTEGER NOT NULL, company_id INTEGER NOT NULL, kind TEXT DEFAULT 'free', at TEXT, PRIMARY KEY(user_id, company_id));
CREATE TABLE IF NOT EXISTS consents(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, subject TEXT, action TEXT, source TEXT, ip TEXT, at TEXT);
CREATE INDEX IF NOT EXISTS idx_consent_user ON consents(user_id);
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY, user_id INTEGER, billed_name TEXT, provider TEXT, method TEXT, amount_paise INTEGER, currency TEXT DEFAULT 'INR',
  status TEXT DEFAULT 'created', provider_order_id TEXT, provider_payment_id TEXT, utr TEXT, plan_days INTEGER, receipt_no TEXT, note TEXT,
  created_at TEXT, paid_at TEXT, reviewed_at TEXT);
CREATE INDEX IF NOT EXISTS idx_pay_user ON payments(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pay_order ON payments(provider_order_id) WHERE provider_order_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_pay_utr ON payments(utr) WHERE utr IS NOT NULL;

"""


# Columns added to `subscribers` (which is now also the user-account table). Added in place so existing databases upgrade themselves.
USER_COLS = [
    ('first_name', 'TEXT'), ('middle_name', 'TEXT'), ('last_name', 'TEXT'),
    ('pan_hash', 'TEXT'), ('pan_enc', 'TEXT'), ('pan_last4', 'TEXT'),
    ('password_hash', 'TEXT'), ('email_verified_at', 'TEXT'), ('phone_verified_at', 'TEXT'), ('terms_at', 'TEXT'),
    ('plan_until', 'TEXT'), ('plan_tier', 'TEXT'), ('login_fails', 'INTEGER DEFAULT 0'), ('locked_until', 'REAL DEFAULT 0'), ('last_login_at', 'TEXT'),
    ('google_sub', 'TEXT'), ('dob', 'TEXT'), ('father_name', 'TEXT'), ('address', 'TEXT'), ('city', 'TEXT'), ('state', 'TEXT'), ('alt_phone', 'TEXT'), ('lang', 'TEXT'),
]


COMPANY_COLS = [('cin', 'TEXT'), ('nse_symbol', 'TEXT'), ('bse_code', 'TEXT'), ('ir_url', 'TEXT'), ('updated_at', 'TEXT')]
LIST_COLS = [('stated_total', 'REAL'), ('validation', 'TEXT'), ('source_doc_id', 'INTEGER')]
SESSION_COLS = [('last_seen', 'REAL')]
RECORD_COLS = [('dp_key', 'TEXT'), ('father', 'TEXT'), ('conf_src', 'TEXT')]


class DB:
    """One SQLite connection per thread. WAL mode so the web server and the worker can run together."""

    def __init__(self, path):
        self.path = path
        if path != ':memory:':
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._local = threading.local()
        self._mem = None
        if path == ':memory:':  # shared single connection for tests
            self._mem = sqlite3.connect(':memory:', check_same_thread=False)
            self._mem.row_factory = sqlite3.Row
            self._lock = threading.RLock()
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._migrate()

    def _migrate(self):
        c = self.conn
        have = {r['name'] for r in c.execute('PRAGMA table_info(subscribers)')}
        for name, typ in USER_COLS:
            if name not in have:
                c.execute('ALTER TABLE subscribers ADD COLUMN %s %s' % (name, typ))
        for tbl, cols in (('companies', COMPANY_COLS), ('lists', LIST_COLS), ('records', RECORD_COLS), ('sessions', SESSION_COLS)):
            have_t = {r['name'] for r in c.execute('PRAGMA table_info(%s)' % tbl)}
            for name, typ in cols:
                if name not in have_t:
                    c.execute('ALTER TABLE %s ADD COLUMN %s %s' % (tbl, name, typ))
        c.execute('CREATE INDEX IF NOT EXISTS idx_rec_dp ON records(dp_key)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_co_isin ON companies(isin)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_co_cin ON companies(cin)')
        pc = {r['name'] for r in c.execute('PRAGMA table_info(payments)')}
        for name, typ in (('tier', 'TEXT'), ('period', 'TEXT')):
            if name not in pc:
                c.execute('ALTER TABLE payments ADD COLUMN %s %s' % (name, typ))
        # rows created by the old anonymous OTP flow were verified on both channels
        c.execute("UPDATE subscribers SET email_verified_at=verified_at, phone_verified_at=verified_at WHERE verified_at IS NOT NULL AND password_hash IS NULL AND email_verified_at IS NULL")
        # one account per email / PAN / mobile (partial indexes: legacy rows without a password are exempt)
        c.execute('DROP INDEX IF EXISTS idx_sub_acct_phone')  # replaced below: accounts made with Google may have no mobile number yet
        for name, col, extra in (('idx_sub_acct_email', 'email', ''), ('idx_sub_acct_pan', 'pan_hash', ''), ('idx_sub_acct_phone2', 'phone', " AND phone<>''"), ('idx_sub_google', 'google_sub', ' AND google_sub IS NOT NULL')):
            try:
                c.execute('CREATE UNIQUE INDEX IF NOT EXISTS %s ON subscribers(%s) WHERE password_hash IS NOT NULL%s' % (name, col, extra))
            except sqlite3.IntegrityError:
                pass
        c.commit()

    @property
    def conn(self):
        if self._mem is not None:
            return self._mem
        c = getattr(self._local, 'c', None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('PRAGMA synchronous=NORMAL')
            c.execute('PRAGMA foreign_keys=OFF')
            self._local.c = c
        return c

    def q(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        return self.conn.execute(sql, args).fetchone()

    def x(self, sql, args=()):
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur

    def many(self, sql, rows):
        self.conn.executemany(sql, rows)

    def commit(self):
        self.conn.commit()

    def meta_get(self, k, default=None):
        r = self.one('SELECT v FROM meta WHERE k=?', (k,))
        return r['v'] if r else default

    def meta_set(self, k, v):
        self.x('INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v', (k, str(v)))
