"""Load company unpaid-dividend lists (PDF / CSV / XLSX / TXT) into the database.

    python3 ingest.py init
    python3 ingest.py load-companies EQUITY_L.csv            # NSE or BSE security master CSV
    python3 ingest.py add list.pdf --company "REC Limited" --url https://... [--fy 2026-27] [--declared 2026-11-14]
    python3 ingest.py stats

Handles the common layouts: one record per line ending in  [pincode] holding amount  (e.g. REC Ltd) and CSV/XLSX tables with a header
row (FOLIO / NAME / ADD1.. / PINCODE / HOLDING / NET DIVIDEND). Name and address are kept together as one text blob because many
companies print them in one column; matching looks at the start of the blob.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys

from config import Settings
from db import DB
from matcher import folio_key, norm_tokens
import registry

TAIL = re.compile(r'^(?P<head>.*?)(?:\s+(?P<pin>\d{6}))?\s+(?P<hold>\d{1,9})\s+(?P<amt>\d{1,3}(?:,\d{2,3})*\.\d{1,2}|\d+\.\d{1,2})\s*$')
TAIL_NOHOLD = re.compile(r'^(?P<head>.*?)(?:\s+(?P<pin>\d{6}))?\s+(?P<amt>\d{1,3}(?:,\d{2,3})*\.\d{1,2}|\d+\.\d{1,2})\s*$')
DT_PREFIX = re.compile(r'^(?P<dt>[A-Za-z0-9 .]*?\bDIV[A-Za-z]*\b\s*(?:\d{4}\s*[-/]\s*\d{2,4})?)\s+(?P<rest>\S.*)$', re.I)
FY_RE = re.compile(r'(\d{4})\s*[-/]\s*(\d{2,4})')
FOLIO_RE = re.compile(r'^[A-Za-z0-9/\-]{4,24}$')


# ---------------------------------------------------------------- reading
PAN_IN_TEXT = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b')


def backfill_pan_tokens(db):
    """One-time: index PAN-shaped words of records loaded before PAN matching existed."""
    if db.meta_get('pan_tok_v1'):
        return 0
    c, n = db.conn, 0
    for r in c.execute('SELECT id, blob FROM records').fetchall():
        for t in set(PAN_IN_TEXT.findall(str(r['blob']).upper())):
            if not c.execute('SELECT 1 FROM rec_tok WHERE token=? AND rec_id=?', (t, r['id'])).fetchone():
                c.execute('INSERT INTO rec_tok(token,rec_id) VALUES(?,?)', (t, r['id']))
                n += 1
    c.commit()
    db.meta_set('pan_tok_v1', '1')
    return n


def backfill_keys(db):
    """One-time: canonical DP-Client ids for records loaded before they existed."""
    if db.meta_get('dp_key_v1'):
        return 0
    c, n = db.conn, 0
    for r in c.execute('SELECT id, folio, blob FROM records WHERE dp_key IS NULL').fetchall():
        k = registry.dp_key(r['folio']) or next(iter(sorted(registry.find_dp_keys('%s %s' % (r['folio'], r['blob'])))), '')
        if k:
            c.execute('UPDATE records SET dp_key=? WHERE id=?', (k, r['id']))
            n += 1
    c.commit()
    db.meta_set('dp_key_v1', '1')
    return n


def read_input(path):
    """-> ('text', str) or ('rows', [[cell,...],...])"""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.pdf':
        return 'text', pdf_text(path)
    if ext in ('.xlsx', '.xlsm'):
        try:
            import openpyxl  # optional dependency
        except ImportError:
            raise RuntimeError('Reading .xlsx needs openpyxl (pip install openpyxl). Or export the sheet as CSV.')
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = []
        for ws in wb.worksheets:
            for r in ws.iter_rows(values_only=True):
                rows.append(['' if c is None else str(c).strip() for c in r])
        return 'rows', rows
    with open(path, 'rb') as f_:
        raw = f_.read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')
    if ext == '.csv' or (text.count(',') > text.count('\n') * 3 and ext != '.txt'):
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel
        return 'rows', [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), dialect)]
    return 'text', text


def pdf_text(path):
    if shutil.which('pdftotext'):
        out = subprocess.run(['pdftotext', '-layout', '-nopgbrk', path, '-'], capture_output=True, check=True)
        return out.stdout.decode('utf-8', 'replace')
    try:
        import pypdf
    except ImportError:
        raise RuntimeError('Reading PDFs needs the pdftotext command (poppler-utils) or the pypdf package.')
    r = pypdf.PdfReader(path)
    return '\n'.join((p.extract_text() or '') for p in r.pages)


# ---------------------------------------------------------------- parsing
def norm_fy(s):
    m = FY_RE.search(s or '')
    if not m:
        return None
    y1, y2 = m.group(1), m.group(2)
    return '%s-%s' % (y1, y2[-2:])


def norm_dtype(s):
    u = (s or '').upper()
    if 'INT' in u:
        return 'Interim'
    if 'FIN' in u:
        return 'Final'
    if 'SPL' in u or 'SPEC' in u:
        return 'Special'
    return 'Dividend'


def _money(x):
    try:
        return float(str(x).replace(',', '').replace('₹', '').strip())
    except ValueError:
        return None


def parse_line(line):
    s = re.sub(r'\s+', ' ', line.strip())
    if len(s) < 12:
        return None
    m = TAIL.match(s)
    hold = None
    if m:
        hold = int(m.group('hold'))
    else:
        m = TAIL_NOHOLD.match(s)
        if not m:
            return None
    head, pin, amt = m.group('head').strip(), m.group('pin'), _money(m.group('amt'))
    if not head or amt is None:
        return None
    dtype = fy = None
    d = DT_PREFIX.match(head)
    if d:
        dtype, fy = norm_dtype(d.group('dt')), norm_fy(d.group('dt'))
        head = d.group('rest')
    parts = head.split(None, 1)
    if len(parts) == 2 and parts[0].isdigit() and len(parts[0]) <= 5:  # serial number column
        p2 = parts[1].split(None, 1)
        if len(p2) == 2 and len(p2[0]) >= 6 and FOLIO_RE.match(p2[0]):
            parts = p2
    if len(parts) < 2:
        return None
    folio, blob = parts
    if not FOLIO_RE.match(folio) or not re.search(r'\d', folio) or not re.search(r'[A-Za-z]{2}', blob):
        return None
    name = addr = None
    k = line.find(folio)
    if k >= 0:  # pdftotext -layout keeps the column gaps: first wide column = name, the rest = address
        segs = [x for x in re.split(r'\s{2,}', line[k + len(folio):].strip()) if x]
        while segs and re.fullmatch(r'[\d.,]+', segs[-1]):
            segs.pop()
        if len(segs) >= 2:
            name, addr = segs[0].strip(), ' '.join(segs[1:]).strip()
    return {'dtype': dtype, 'fy': fy, 'folio': folio, 'blob': blob.strip(), 'pincode': pin or '', 'holding': hold, 'amount': amt, 'name': name, 'addr': addr}


def parse_text(text):
    rows, skipped = [], []
    for line in text.splitlines():
        if not line.strip():
            continue
        r = parse_line(line)
        if r:
            rows.append(r)
        else:
            skipped.append(line.strip()[:80])
    return rows, skipped


def _map_headers(hdr):
    cols = {'folio': [], 'name': None, 'addr': [], 'pin': None, 'hold': None, 'amt': None, 'type': None, 'fy': None, 'father': None}
    amt_rank = None
    for i, h in enumerate(hdr):
        u = re.sub(r'[^A-Z0-9 ]', ' ', h.upper())
        if 'TYPE' in u:
            cols['type'] = i
        elif re.search(r'\b(YEAR|FY|F Y)\b', u):
            cols['fy'] = i
        elif 'FOLIO' in u or re.search(r'\b(DP|CLIENT|BENEF\w*)\b', u):
            cols['folio'].append(i)
        elif 'FATHER' in u or 'HUSBAND' in u or 'GUARDIAN' in u:
            cols['father'] = i
        elif 'NAME' in u and 'FATHER' not in u and 'COMPANY' not in u and cols['name'] is None:
            cols['name'] = i
        elif 'ADD' in u:
            cols['addr'].append(i)
        elif 'PIN' in u:
            cols['pin'] = i
        elif re.search(r'HOLDING|SHARES|QTY|QUANTITY', u):
            cols['hold'] = i
        elif re.search(r'NET|AMOUNT|DIVIDEND|AMT', u) and not re.search(r'DATE|RATE|PER', u):
            rank = 0 if 'NET' in u else 1 if 'AMOUNT' in u or 'AMT' in u else 2
            if amt_rank is None or rank < amt_rank:
                cols['amt'], amt_rank = i, rank
    return cols


def parse_rows(rows):
    hdr_i = None
    for i, r in enumerate(rows[:40]):
        up = ' '.join(r).upper()
        if sum(1 for c in r if c) >= 3 and 'NAME' in up and re.search(r'AMOUNT|DIVIDEND|AMT', up):
            hdr_i = i
            break
    if hdr_i is None:  # no header: treat each row as a text line
        return parse_text('\n'.join(' '.join(c for c in r if c) for r in rows))
    cols = _map_headers(rows[hdr_i])
    if cols['name'] is None or cols['amt'] is None or not cols['folio']:
        return parse_text('\n'.join(' '.join(c for c in r if c) for r in rows[hdr_i + 1:]))
    out, skipped = [], []

    def cell(r, i):
        return r[i].strip() if i is not None and i < len(r) and r[i] is not None else ''

    for r in rows[hdr_i + 1:]:
        if not any(r):
            continue
        amt = _money(cell(r, cols['amt']))
        folio = ''.join(cell(r, i) for i in cols['folio']).replace(' ', '')
        name = cell(r, cols['name'])
        if amt is None or not folio or not name:
            skipped.append(' '.join(r)[:80])
            continue
        addr = ' '.join(cell(r, i) for i in cols['addr'] if cell(r, i))
        father = cell(r, cols['father'])
        pin = re.sub(r'\D', '', cell(r, cols['pin']))[:6]
        if len(pin) != 6:
            m = re.search(r'\b\d{6}\b', addr)
            pin = m.group(0) if m else ''
        h = _money(cell(r, cols['hold']))
        t = cell(r, cols['type'])
        out.append({'dtype': norm_dtype(t) if t else None, 'fy': norm_fy(t) or norm_fy(cell(r, cols['fy'])), 'folio': folio, 'blob': re.sub(r'\s+', ' ', (name + ' ' + addr).strip()),
                    'pincode': pin, 'holding': int(h) if h is not None else None, 'amount': amt, 'father': father, 'name': name or None, 'addr': addr or None})
    return out, skipped


# ---------------------------------------------------------------- dates
def add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def estimate_declared(fy, dtype):
    """Rough declaration date when the list does not say. Final dividends are voted at the AGM (about Aug-Sep after the FY ends);
    interim dividends are usually declared in Oct-Feb of the FY. Always shown to users as an estimate."""
    try:
        y = int(fy[:4])
    except (TypeError, ValueError):
        return None
    if (dtype or '').lower() == 'final':
        return dt.date(y + 1, 9, 1)
    return dt.date(y, 11, 15)


def due_from_declared(declared):
    """Dividend not claimed within 30 days goes to the Unpaid Dividend Account within 7 days; 7 years later it moves to IEPF."""
    if not declared:
        return None
    return add_years(declared + dt.timedelta(days=37), 7)


# ---------------------------------------------------------------- database
def get_company(db, name, **kw):
    name = re.sub(r'\s+', ' ', name.strip())
    r = db.one('SELECT id FROM companies WHERE lower(name)=lower(?)', (name,))
    if r:
        return r['id']
    cur = db.x('INSERT INTO companies(name,symbol,isin,website) VALUES(?,?,?,?)', (name, kw.get('symbol'), kw.get('isin'), kw.get('website')))
    return cur.lastrowid


def load_companies_csv(db, path):
    raw = open(path, 'rb').read().decode('utf-8-sig', 'replace')
    rd = csv.DictReader(io.StringIO(raw))
    n = 0
    for row in rd:
        row = {(k or '').strip().upper(): (v or '').strip() for k, v in row.items()}
        name = row.get('NAME OF COMPANY') or row.get('SECURITY NAME') or row.get('ISSUER NAME') or row.get('COMPANY NAME') or row.get('NAME')
        if not name:
            continue
        sym = row.get('SYMBOL') or row.get('SECURITY ID') or row.get('SECURITY CODE')
        isin = row.get('ISIN NUMBER') or row.get('ISIN NO') or row.get('ISIN')
        get_company(db, name, symbol=sym, isin=isin)
        n += 1
    return n


STATED_RE = re.compile(r'(?:GRAND\s+TOTAL|TOTAL(?:\s+AMOUNT)?)\D{0,12}?((?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?)\s*$', re.I | re.M)


def stated_total(kind, content):
    """The total the company itself prints (if any), used to check that every row was read."""
    if kind == 'rows':
        text = '\n'.join(' '.join(c for c in r if c) for r in content)
    else:
        text = content
    vals = [_money(m.group(1)) for m in STATED_RE.finditer(text)]
    vals = [v for v in vals if v]
    return max(vals) if vals else None


def validate(parsed_total, stated, n_rows, n_skipped):
    """-> 'ok' | 'mismatch' | 'unverified' | 'partial'. A list whose parsed total differs from its printed total is flagged, never trusted silently."""
    if stated:
        if abs(parsed_total - stated) <= max(1.0, stated * 0.001):
            return 'ok'
        return 'partial' if parsed_total < stated else 'mismatch'
    return 'unverified'  # skipped lines are mostly titles and headings, so they cannot prove a gap


def ingest_file(db, company, path, fy=None, dtype=None, source_url='', declared_on=None, source_doc_id=None):
    """Parse one list and store it. Returns a summary dict. Duplicate files are ignored (by content hash)."""
    with open(path, 'rb') as fh:
        data = fh.read()
    fh = hashlib.sha256(data + company.lower().encode()).hexdigest()
    if db.one('SELECT id FROM lists WHERE file_hash=?', (fh,)):
        return {'status': 'duplicate', 'rows': 0}
    kind, content = read_input(path)
    rows, skipped = parse_rows(content) if kind == 'rows' else parse_text(content)
    if not rows:
        return {'status': 'error', 'error': 'No records recognised. Check the file layout (see README -> Supported layouts).', 'rows': 0, 'skipped': len(skipped), 'skipped_sample': skipped[:5]}
    fy = fy or _mode([r['fy'] for r in rows])
    dtype = dtype or _mode([r['dtype'] for r in rows]) or 'Dividend'
    declared = dt.date.fromisoformat(declared_on) if declared_on else estimate_declared(fy, dtype)
    due = due_from_declared(declared)
    cid = get_company(db, company)
    stated = stated_total(kind, content)
    cur = db.x('INSERT INTO lists(company_id,fy,dtype,source_url,declared_on,iepf_due,ingested_at,file_hash,stated_total,source_doc_id) VALUES(?,?,?,?,?,?,?,?,?,?)',
               (cid, fy, dtype, source_url, declared.isoformat() if declared else None, due.isoformat() if due else None, dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds'), fh, stated, source_doc_id))
    lid = cur.lastrowid
    n = 0
    total = 0.0
    c = db.conn
    for r in rows:
        rh = hashlib.sha1(('%s|%s|%s|%s|%s' % (lid, r['folio'], r['blob'], r['amount'], r['holding'])).encode()).hexdigest()
        dpk = registry.dp_key(r['folio']) or next(iter(sorted(registry.find_dp_keys(r['folio'] + ' ' + r['blob']))), '')
        cur = c.execute('INSERT OR IGNORE INTO records(list_id,company_id,folio,folio_key,blob,pincode,holding,amount,rowhash,dp_key,father,name,addr) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (lid, cid, r['folio'], folio_key(r['folio']), r['blob'], r['pincode'], r['holding'], r['amount'], rh, dpk or None, (r.get('father') or None), r.get('name'), r.get('addr')))
        if cur.rowcount:
            n += 1
            total += r['amount']
            toks = {t for t in norm_tokens(r['blob'])[:8] if len(t) >= 3} | set(PAN_IN_TEXT.findall(str(r['blob']).upper()))  # PANs anywhere in the row are indexed
            c.executemany('INSERT INTO rec_tok(token,rec_id) VALUES(?,?)', [(t, cur.lastrowid) for t in toks])
    val = validate(total, stated, n, len(skipped))
    c.execute('UPDATE lists SET n_rows=?, total=?, validation=? WHERE id=?', (n, total, val, lid))
    c.commit()
    db.meta_set('last_ingest_at', dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds'))
    return {'status': 'ok', 'list_id': lid, 'rows': n, 'total': round(total, 2), 'fy': fy, 'dtype': dtype, 'declared_on': declared.isoformat() if declared else None,
            'iepf_due_est': due.isoformat() if due else None, 'skipped': len(skipped), 'skipped_sample': skipped[:3], 'stated_total': stated, 'validation': val}


def _mode(vals):
    vals = [v for v in vals if v]
    if not vals:
        return None
    return max(set(vals), key=vals.count)


def stats(db):
    r = db.one('SELECT COUNT(*) n, COALESCE(SUM(amount),0) t FROM records')
    return {'companies_covered': db.one('SELECT COUNT(DISTINCT company_id) n FROM lists')['n'], 'companies_known': db.one('SELECT COUNT(*) n FROM companies')['n'],
            'lists': db.one('SELECT COUNT(*) n FROM lists')['n'], 'records': r['n'], 'amount': round(r['t'], 2), 'last_ingest_at': db.meta_get('last_ingest_at')}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('init')
    p = sub.add_parser('load-companies')
    p.add_argument('csv')
    p = sub.add_parser('add')
    p.add_argument('file')
    p.add_argument('--company', required=True)
    p.add_argument('--fy')
    p.add_argument('--type', dest='dtype')
    p.add_argument('--url', default='')
    p.add_argument('--declared')
    sub.add_parser('stats')
    a = ap.parse_args(argv)
    st = Settings()
    db = DB(st.db_path)
    if a.cmd == 'init':
        print('database ready at', st.db_path)
    elif a.cmd == 'load-companies':
        print('companies loaded:', load_companies_csv(db, a.csv))
    elif a.cmd == 'add':
        print(ingest_file(db, a.company, a.file, a.fy, a.dtype, a.url, a.declared))
    elif a.cmd == 'stats':
        print(stats(db))


if __name__ == '__main__':
    main()
