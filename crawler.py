"""Polite crawler for company unpaid-dividend pages.

For every active row in crawl_targets (a company's investor / unclaimed-dividend page, or a direct list file) it:
  1. checks robots.txt, waits between requests to the same host, sends an honest User-Agent;
  2. fetches the page and skips everything if its content hash did not change;
  3. finds links to PDF / XLSX / XLS / CSV files that look like unpaid / unclaimed dividend lists;
  4. downloads each new file, records it in source_docs (url, fetched_at, hash, parse report) and ingests it.

    python3 crawler.py run [--limit 20]        # process targets that are due
    python3 crawler.py add "REC Limited" https://example.com/unclaimed-dividend
"""
import hashlib
import html.parser
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import datetime as dt

import ingest
import registry

UA = 'DhanKhojBot/1.0 (+https://dhankhoj.in/bot; unclaimed dividend lists published by companies)'
MAX_BYTES = 40 * 1024 * 1024
DOC_EXT = ('.pdf', '.xlsx', '.xlsm', '.xls', '.csv', '.txt')
WANT = re.compile(r'unclaim|unpaid|dividend|iepf|investor', re.I)
RECHECK_HOURS = 24
HOST_DELAY = 2.0
_last_hit = {}
_robots = {}


def _now():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')


class _Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._href, self._txt = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self._href = dict(attrs).get('href')
            self._txt = []

    def handle_data(self, data):
        if self._href is not None:
            self._txt.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self._href is not None:
            self.links.append((self._href, ' '.join(''.join(self._txt).split())))
            self._href = None


def extract_links(base, body):
    p = _Links()
    try:
        p.feed(body)
    except Exception:
        pass
    out, seen = [], set()
    for href, text in p.links:
        if not href or href.startswith(('#', 'mailto:', 'javascript:')):
            continue
        u = urllib.parse.urljoin(base, href.strip()).split('#')[0]
        if not u.lower().startswith(('http://', 'https://')) or u in seen:
            continue
        path = urllib.parse.urlparse(u).path.lower()
        if path.endswith(DOC_EXT) and (WANT.search(text) or WANT.search(path)):
            seen.add(u)
            out.append((u, text))
    return out


def allowed(url, opener=None):
    p = urllib.parse.urlparse(url)
    host = '%s://%s' % (p.scheme, p.netloc)
    rp = _robots.get(host)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(host + '/robots.txt', headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                rp.parse(r.read(200000).decode('utf-8', 'replace').splitlines())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                rp.disallow_all = True
            else:
                rp.parse([])  # no robots.txt = allowed
        except Exception:
            rp.parse([])
        _robots[host] = rp
    return rp.can_fetch(UA, url)


def fetch(url, delay=HOST_DELAY):
    """-> (bytes, content_type). Raises RuntimeError with a plain reason."""
    if not allowed(url):
        raise RuntimeError('blocked by robots.txt')
    host = urllib.parse.urlparse(url).netloc
    wait = _last_hit.get(host, 0) + delay - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(MAX_BYTES + 1)
            ct = r.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        raise RuntimeError('HTTP %s' % e.code)
    except Exception as e:
        raise RuntimeError('fetch failed: %s' % (str(e)[:80]))
    if len(data) > MAX_BYTES:
        raise RuntimeError('file too large')
    return data, ct


def _ext(url, ct):
    e = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if e in DOC_EXT:
        return e
    c = ct.lower()
    return '.pdf' if 'pdf' in c else '.xlsx' if 'spreadsheetml' in c else '.csv' if 'csv' in c else '.html' if 'html' in c else e


def process_document(db, company_id, company_name, url, data, ext, data_dir, label=''):
    """Store a fetched list file, log provenance, ingest it. Returns the source_docs id."""
    h = hashlib.sha256(data).hexdigest()
    dup = db.one('SELECT id FROM source_docs WHERE company_id=? AND content_hash=?', (company_id, h))
    if dup:
        return dup['id'], 'unchanged'
    folder = os.path.join(data_dir, 'sources', str(company_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, h[:16] + ext)
    with open(path, 'wb') as fh:
        fh.write(data)
    cur = db.x('INSERT INTO source_docs(company_id,url,fetched_at,content_hash,bytes,kind,status) VALUES(?,?,?,?,?,?,?)',
               (company_id, url, _now(), h, len(data), ext.lstrip('.'), 'fetched'))
    sid = cur.lastrowid
    fy = ingest.norm_fy(label) or ingest.norm_fy(urllib.parse.unquote(url))
    try:
        res = ingest.ingest_file(db, company_name, path, fy=fy, source_url=url, source_doc_id=sid)
    except Exception as e:
        res = {'status': 'error', 'error': str(e)[:200], 'rows': 0}
    status = {'ok': 'parsed', 'duplicate': 'duplicate'}.get(res.get('status'), 'failed')
    db.x('UPDATE source_docs SET status=?, rows_parsed=?, rows_skipped=?, parsed_total=?, stated_total=?, validation=?, report=?, list_id=? WHERE id=?',
         (status, res.get('rows', 0), res.get('skipped', 0), res.get('total'), res.get('stated_total'), res.get('validation'), (res.get('error') or '')[:300], res.get('list_id'), sid))
    return sid, status


def crawl_target(db, t, data_dir):
    """One target. -> dict summary. Never raises."""
    co = db.one('SELECT id, name FROM companies WHERE id=?', (t['company_id'],))
    out = {'url': t['url'], 'docs': 0, 'parsed': 0, 'status': 'ok'}
    try:
        data, ct = fetch(t['url'])
        ext = _ext(t['url'], ct)
        h = hashlib.sha256(data).hexdigest()
        if h == t['last_hash']:
            out['status'] = 'unchanged'
        elif ext in DOC_EXT:  # the target is itself a list file
            _, st = process_document(db, co['id'], co['name'], t['url'], data, ext, data_dir)
            out['docs'] = 1
            out['parsed'] = 1 if st == 'parsed' else 0
        else:
            body = data.decode('utf-8', 'replace')
            for u, label in extract_links(t['url'], body)[:40]:
                if db.one('SELECT 1 FROM source_docs WHERE company_id=? AND url=? AND status IN (\'parsed\',\'duplicate\')', (co['id'], u)):
                    continue
                try:
                    d, c2 = fetch(u)
                except RuntimeError as e:
                    out['status'] = 'partial: %s' % e
                    continue
                _, st = process_document(db, co['id'], co['name'], u, d, _ext(u, c2), data_dir, label)
                out['docs'] += 1
                out['parsed'] += 1 if st == 'parsed' else 0
        db.x('UPDATE crawl_targets SET last_checked=?, last_hash=?, last_status=?, last_error=NULL, fails=0, next_check=? WHERE id=?',
             (_now(), h, out['status'], time.time() + RECHECK_HOURS * 3600, t['id']))
    except RuntimeError as e:
        out['status'] = 'error'
        out['error'] = str(e)
        fails = (t['fails'] or 0) + 1
        back = min(RECHECK_HOURS * 3600 * (2 ** min(fails, 5)), 14 * 86400)  # back off on repeated failure
        db.x('UPDATE crawl_targets SET last_checked=?, last_status=?, last_error=?, fails=?, next_check=? WHERE id=?',
             (_now(), 'error', str(e)[:200], fails, time.time() + back, t['id']))
    return out


def crawl_due(db, data_dir, limit=20):
    rows = db.q('SELECT * FROM crawl_targets WHERE active=1 AND next_check<=? ORDER BY next_check LIMIT ?', (time.time(), limit))
    return [crawl_target(db, t, data_dir) for t in rows]


def main(argv=None):
    from config import Settings
    from db import DB
    a = argv if argv is not None else sys.argv[1:]
    st = Settings()
    db = DB(st.db_path)
    data_dir = os.path.dirname(os.path.abspath(st.db_path))
    if a[:1] == ['run']:
        lim = int(a[a.index('--limit') + 1]) if '--limit' in a else 20
        for r in crawl_due(db, data_dir, lim):
            print(r)
    elif a[:1] == ['add'] and len(a) >= 3:
        cid, _ = registry.upsert_company(db, a[1])
        print('target', registry.add_crawl_target(db, cid, a[2]))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
