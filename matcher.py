"""Name / folio matching, masking and small formatting helpers (pure functions, no I/O except candidate lookup)."""
import re
from difflib import SequenceMatcher

TITLES = {'MR', 'MRS', 'MS', 'MISS', 'SHRI', 'SMT', 'SRI', 'SHREE', 'KUM', 'DR', 'LATE', 'SHRIMATI', 'PROF', 'ADV'}  # single letters are initials and are kept


def norm_tokens(text, drop_titles=True):
    t = re.sub(r'[^A-Z0-9]+', ' ', str(text or '').upper()).split()
    if drop_titles:
        t = [x for x in t if x not in TITLES or len(t) <= 2]
    return t


def folio_key(s):
    return re.sub(r'[^A-Z0-9]', '', str(s or '').upper())


def _close(a, b):
    if a == b:
        return 2
    if len(a) == 1 and b.startswith(a):
        return 1
    if len(b) == 1 and a.startswith(b):
        return 1
    if len(a) >= 4 and len(b) >= 4 and a[0] == b[0] and SequenceMatcher(None, a, b).ratio() >= 0.86:
        return 1.5
    return 0


def score_name(user_tokens, blob_tokens):
    """Order-insensitive match of the user's name tokens against the START of the record text (name comes first, then address).
    Returns (fraction matched, number of strong >=3-letter matches, number of exact matches)."""
    if not user_tokens:
        return 0.0, 0, 0
    window = blob_tokens[:max(len(user_tokens) + 3, 4)]
    used = set()
    matched = strong = exact = 0
    for u in user_tokens:
        best = None
        for i, r in enumerate(window):
            if i in used:
                continue
            c = _close(u, r)
            if c and (best is None or c > best[1]):
                best = (i, c)
        if best:
            used.add(best[0])
            matched += 1
            if best[1] == 2:
                exact += 1
            if len(u) >= 3:
                strong += 1
    return matched / len(user_tokens), strong, exact


def classify(user, rec):
    """user: {'tokens':[...], 'pincode':str, 'folios':set}  rec: {'blob_tokens', 'pincode', 'folio_key'}
    -> (confidence 'high'|'medium'|'low'|None, score)."""
    if rec['folio_key'] and rec['folio_key'] in user['folios']:
        return 'high', 1.0
    if user.get('pan') and user['pan'] in rec['blob_tokens']:  # the PAN is a unique key: a list row that carries it is this person
        return 'high', 1.0
    ut = user['tokens']
    s, strong, exact = score_name(ut, rec['blob_tokens'])
    if s < 0.66 or strong < 1:
        return None, s
    pin_user, pin_rec = user.get('pincode') or '', rec.get('pincode') or ''
    pin_eq = bool(pin_user and pin_rec and pin_user == pin_rec)
    pin_ne = bool(pin_user and pin_rec and pin_user != pin_rec)
    if len(ut) >= 2 and s == 1.0 and strong >= min(2, len(ut)):
        conf = 'high' if pin_eq and exact >= 2 else 'medium'
        if pin_ne:
            conf = 'low'
        return conf, s
    if len(ut) >= 2 and s >= 0.66:
        return 'low', s
    return ('low' if s == 1.0 else None), s  # single-word names are too ambiguous for an alert


def candidate_ids(db, tokens, cap=30000):
    """Record ids whose first tokens contain one of the user's longest tokens (exact or same 4-letter prefix)."""
    toks = sorted({t for t in tokens if len(t) >= 3}, key=len, reverse=True)[:2]
    ids = set()
    for t in toks:
        pre = t[:4]
        rows = db.q('SELECT rec_id FROM rec_tok WHERE token>=? AND token<? LIMIT ?', (pre, pre + '￿', cap))
        ids.update(r['rec_id'] for r in rows)
        if len(ids) >= cap:
            break
    return ids


def load_records(db, ids):
    ids = list(ids)
    out = []
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        ph = ','.join('?' * len(part))
        for r in db.q('SELECT r.*, c.name AS company, l.fy, l.dtype, l.iepf_due, l.source_url, l.declared_on FROM records r '
                      'JOIN companies c ON c.id=r.company_id JOIN lists l ON l.id=r.list_id WHERE r.id IN (%s)' % ph, part):
            out.append(r)
    return out


def user_profile(name, aliases=(), pincode='', folios=(), pan=''):
    names = [name] + list(aliases or [])
    return [{'tokens': norm_tokens(n), 'pincode': (pincode or '').strip(), 'folios': {folio_key(f) for f in (folios or []) if folio_key(f)}, 'pan': (pan or '').upper()} for n in names if norm_tokens(n)]


def find_matches(db, name, aliases=(), pincode='', folios=(), limit=200, pan=''):
    """All records that plausibly belong to this person: [(row, conf, score)] best first."""
    profs = user_profile(name, aliases, pincode, folios, pan)
    found = {}
    for p in profs:
        ids = candidate_ids(db, p['tokens'])
        for fk in p['folios']:
            ids.update(r['id'] for r in db.q('SELECT id FROM records WHERE folio_key=?', (fk,)))
        if p['pan']:
            ids.update(r['rec_id'] for r in db.q('SELECT rec_id FROM rec_tok WHERE token=?', (p['pan'],)))
        for r in load_records(db, ids):
            rec = {'blob_tokens': norm_tokens(r['blob'], drop_titles=True), 'pincode': r['pincode'] or '', 'folio_key': r['folio_key']}
            conf, sc = classify(p, rec)
            if conf:
                cur = found.get(r['id'])
                rank = {'high': 3, 'medium': 2, 'low': 1}
                if not cur or rank[conf] > rank[cur[1]]:
                    found[r['id']] = (r, conf, sc)
    rank = {'high': 3, 'medium': 2, 'low': 1}
    res = sorted(found.values(), key=lambda x: (-rank[x[1]], -x[2], -(x[0]['amount'] or 0)))
    return res[:limit]


# ---------- masking / formatting ----------
def mask_word(w):
    return w[:1] + '*' * max(len(w) - 1, 0)


def mask_name_from_blob(blob, n):
    toks = [t for t in re.split(r'\s+', (blob or '').strip()) if t][:max(n, 1)]
    return ' '.join(mask_word(re.sub(r'[^A-Za-z]', '', t) or t) for t in toks)


def mask_folio(f):
    f = str(f or '')
    return ('*' * max(len(f) - 4, 0)) + f[-4:]


BANDS = [(0, 100), (100, 500), (500, 1000), (1000, 5000), (5000, 10000), (10000, 50000), (50000, 100000), (100000, 1000000)]


def amount_band(a):
    a = float(a or 0)
    for lo, hi in BANDS:
        if a < hi:
            return '₹%s–₹%s' % (inr_plain(lo), inr_plain(hi))
    return 'over ₹10,00,000'


def inr_plain(n):
    s = str(int(round(n)))
    if len(s) <= 3:
        return s
    rest, last3 = s[:-3], s[-3:]
    rest = re.sub(r'\B(?=(\d{2})+(?!\d))', ',', rest)
    return rest + ',' + last3


def inr(n, dp=0):
    n = float(n or 0)
    if dp:
        i, d = ('%.*f' % (dp, abs(n))).split('.')
        return '₹' + inr_plain(int(i)) + '.' + d
    return '₹' + inr_plain(abs(n))
