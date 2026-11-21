"""Company registry + canonical search keys.

The legal duty to publish unpaid-dividend lists sits with each company (identified by CIN), so the registry is company-centric.
NSE and BSE security-master files are only used to discover companies and merge them on ISIN.

    python3 registry.py import EQUITY_L.csv            # NSE master (SYMBOL, NAME OF COMPANY, ISIN NUMBER ...)
    python3 registry.py import bse_list.csv            # BSE master (Security Code, Issuer Name, ISIN No ...)
    python3 registry.py import mca.csv                 # optional: CIN, company name, website
    python3 registry.py show
"""
import csv
import datetime as dt
import io
import re
import sys

ISIN_RE = re.compile(r'^IN[A-Z0-9]{10}$')
CIN_RE = re.compile(r'^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$')
DPCLIENT_RE = re.compile(r'(?:IN\d{6}|\d{8})\d{8}')  # CDSL: 16 digits; NSDL: IN + 6 digits + 8 digits


def now():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')


# ------------------------------------------------------------------ canonical keys
def dp_key(s):
    """Canonical DP Id + Client Id: upper-case alphanumerics only. 'IN300123-12345678' -> 'IN30012312345678'.
    Returns '' unless the result looks like a 16-character demat account id."""
    k = re.sub(r'[^A-Z0-9]', '', str(s or '').upper())
    return k if re.fullmatch(r'(?:IN[0-9A-Z]{6}|[0-9]{8})[0-9]{8}', k) else ''


def find_dp_keys(text):
    """Every demat-account-shaped id inside free text (folio columns often carry them with dashes or spaces)."""
    out = set()
    for m in re.finditer(r'(?:IN\s*\d{6}|\b\d{8})[\s\-]*\d{8}\b', str(text or '').upper()):
        k = dp_key(m.group(0))
        if k:
            out.add(k)
    return out


def norm_isin(s):
    s = re.sub(r'\s', '', str(s or '').upper())
    return s if ISIN_RE.match(s) else ''


def norm_cin(s):
    s = re.sub(r'\s', '', str(s or '').upper())
    return s if CIN_RE.match(s) else ''


def name_key(name):
    """Company-name key for fuzzy joins when no ISIN is available."""
    n = re.sub(r'[^A-Z0-9 ]', ' ', str(name or '').upper())
    n = re.sub(r'\b(LIMITED|LTD|PVT|PRIVATE|THE|COMPANY|CO)\b', ' ', n)
    return re.sub(r'\s+', ' ', n).strip()


# ------------------------------------------------------------------ registry
def _field(row, *names):
    for n in names:
        v = row.get(n)
        if v:
            return v.strip()
    return ''


def find_company(db, name='', isin='', cin='', nse='', bse=''):
    """Best existing company row for these identifiers (ISIN > CIN > NSE symbol > BSE code > exact name > normalised name)."""
    if isin:
        r = db.one('SELECT * FROM companies WHERE isin=?', (isin,))
        if r:
            return r
    if cin:
        r = db.one('SELECT * FROM companies WHERE cin=?', (cin,))
        if r:
            return r
    if nse:
        r = db.one('SELECT * FROM companies WHERE nse_symbol=?', (nse,))
        if r:
            return r
    if bse:
        r = db.one('SELECT * FROM companies WHERE bse_code=?', (bse,))
        if r:
            return r
    if name:
        r = db.one('SELECT * FROM companies WHERE lower(name)=lower(?)', (re.sub(r'\s+', ' ', name.strip()),))
        if r:
            return r
        k = name_key(name)
        if k:
            for r in db.q('SELECT * FROM companies WHERE isin IS NULL OR isin=\'\' OR cin IS NULL OR cin=\'\''):
                if name_key(r['name']) == k:
                    return r
    return None


def upsert_company(db, name, isin='', cin='', nse='', bse='', website='', ir_url=''):
    """Insert or merge. Existing non-empty values are kept unless the new source supplies a validated identifier for an empty slot."""
    name = re.sub(r'\s+', ' ', (name or '').strip())
    isin, cin = norm_isin(isin), norm_cin(cin)
    if not (name or isin or cin):
        return None, 'skip'
    row = find_company(db, name, isin, cin, nse, bse)
    if row is None:
        cur = db.x('INSERT INTO companies(name,symbol,isin,website,cin,nse_symbol,bse_code,ir_url,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                   (name or isin, nse or bse or None, isin or None, website or None, cin or None, nse or None, bse or None, ir_url or None, now()))
        return cur.lastrowid, 'new'
    sets, args = [], []
    for col, val in (('isin', isin), ('cin', cin), ('nse_symbol', nse), ('bse_code', bse), ('website', website), ('ir_url', ir_url)):
        if val and not (row[col] or ''):
            sets.append('%s=?' % col)
            args.append(val)
    if nse and not (row['symbol'] or ''):
        sets.append('symbol=?')
        args.append(nse)
    if sets:
        sets.append('updated_at=?')
        args += [now(), row['id']]
        db.x('UPDATE companies SET %s WHERE id=?' % ','.join(sets), args)
        return row['id'], 'merged'
    return row['id'], 'same'


def import_master(db, path_or_text, is_text=False):
    """Import an NSE / BSE / MCA style CSV. Header names are matched by vocabulary, so the exchange files work as downloaded."""
    raw = path_or_text if is_text else open(path_or_text, 'rb').read().decode('utf-8-sig', 'replace')
    rd = csv.DictReader(io.StringIO(raw))
    res = {'new': 0, 'merged': 0, 'same': 0, 'skip': 0, 'bad_isin': 0}
    for row in rd:
        row = {re.sub(r'\s+', ' ', (k or '').strip().upper()): (v or '').strip() for k, v in row.items()}
        name = _field(row, 'NAME OF COMPANY', 'ISSUER NAME', 'SECURITY NAME', 'COMPANY NAME', 'NAME')
        isin_raw = _field(row, 'ISIN NUMBER', 'ISIN NO', 'ISIN NO.', 'ISIN')
        isin = norm_isin(isin_raw)
        if isin_raw and not isin:
            res['bad_isin'] += 1
        cin = norm_cin(_field(row, 'CIN', 'CORPORATE IDENTIFICATION NUMBER', 'CIN NUMBER'))
        sym = _field(row, 'SYMBOL', 'NSE SYMBOL')
        code = _field(row, 'SECURITY CODE', 'BSE CODE', 'SCRIP CODE')
        sec_id = _field(row, 'SECURITY ID')
        bse = code if code.isdigit() else ''
        nse = sym.upper() if sym else ''
        if not nse and sec_id and not sec_id.isdigit() and not bse:
            nse = ''
        site = _field(row, 'WEBSITE', 'COMPANY WEBSITE', 'URL')
        ir = _field(row, 'IR URL', 'INVESTOR URL', 'UNPAID DIVIDEND URL')
        _, how = upsert_company(db, name, isin, cin, nse, bse, site, ir)
        res[how] = res.get(how, 0) + 1
    return res


def add_crawl_target(db, company_id, url, kind='page'):
    url = (url or '').strip()
    if not re.match(r'^https?://', url, re.I):
        return None
    db.x('INSERT OR IGNORE INTO crawl_targets(company_id,url,kind) VALUES(?,?,?)', (company_id, url, kind))
    return db.one('SELECT id FROM crawl_targets WHERE url=?', (url,))['id']


def registry_stats(db):
    n = lambda sql: db.one(sql)['n']
    return {'companies': n('SELECT COUNT(*) n FROM companies'),
            'with_isin': n("SELECT COUNT(*) n FROM companies WHERE isin<>'' AND isin IS NOT NULL"),
            'with_cin': n("SELECT COUNT(*) n FROM companies WHERE cin<>'' AND cin IS NOT NULL"),
            'on_nse': n("SELECT COUNT(*) n FROM companies WHERE nse_symbol<>'' AND nse_symbol IS NOT NULL"),
            'on_bse': n("SELECT COUNT(*) n FROM companies WHERE bse_code<>'' AND bse_code IS NOT NULL"),
            'crawl_targets': n('SELECT COUNT(*) n FROM crawl_targets WHERE active=1')}


def main(argv=None):
    from config import Settings
    from db import DB
    a = argv if argv is not None else sys.argv[1:]
    db = DB(Settings().db_path)
    if len(a) >= 2 and a[0] == 'import':
        print(import_master(db, a[1]))
    elif a[:1] == ['show']:
        print(registry_stats(db))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
