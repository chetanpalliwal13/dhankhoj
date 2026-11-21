"""Business logic: public check, subscribe + OTP verification, matching, alerts, reminders, outbox, privacy tools."""
import datetime as dt
import hashlib
import os
import hmac
import json
import re
import secrets
import time

import ingest
import matcher as M
import plans

EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$')
REMINDER_STAGES = (365, 180, 90, 30, 7)


class ApiError(Exception):
    def __init__(self, msg, code=400, **extra):
        super().__init__(msg)
        self.msg, self.code, self.extra = msg, code, extra


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')


def clean_name(s):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    s = re.sub(r"[^A-Za-z .'\-]", '', s)
    if len(s) < 3 or len(s) > 80 or not re.search(r'[A-Za-z]{2}', s):
        raise ApiError('Please enter your full name exactly as it appears on your share certificate / demat account.')
    return s


def norm_phone(s):
    d = re.sub(r'\D', '', str(s or ''))
    if len(d) == 12 and d.startswith('91'):
        d = d[2:]
    elif len(d) == 11 and d.startswith('0'):
        d = d[1:]
    if not re.fullmatch(r'[6-9]\d{9}', d):
        raise ApiError('Enter a valid 10-digit Indian mobile number.')
    return '+91' + d


def norm_email(s):
    s = str(s or '').strip().lower()
    if not EMAIL_RE.match(s) or len(s) > 120:
        raise ApiError('Enter a valid email address.')
    return s


def clean_pin(s):
    s = re.sub(r'\D', '', str(s or ''))
    if s and len(s) != 6:
        raise ApiError('PIN code must be 6 digits (or leave it blank).')
    return s


def clean_folios(lst, maximum=5):
    """Demat account (DP ID + Client ID, e.g. IN30047610123456) or folio numbers: normalised, de-duplicated, at most `maximum`."""
    out = []
    for f in (lst or []):
        k = M.folio_key(f)
        if k:
            if not 4 <= len(k) <= 24:
                raise ApiError('"%s" does not look like a DP-Client ID or folio number (4-24 letters and digits).' % str(f)[:30])
            if k not in out:
                out.append(k)
    if len(out) > maximum:
        raise ApiError('You can save up to %d DP-Client IDs / folio numbers.' % maximum)
    return out


def mask_email(e):
    u, d = e.split('@')
    return u[:1] + '***@' + d


def mask_phone(p):
    if not p:
        return ''
    return p[:3] + '*****' + p[-2:]


_PANRE = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b')


def days_left(iso):
    if not iso:
        return None
    return (dt.date.fromisoformat(iso) - dt.date.today()).days


class Service:
    def __init__(self, db, st, notifier):
        self.db, self.st, self.n = db, st, notifier
        from auth import Vault  # runtime import: auth imports this module
        self.vault = Vault(st.data_key or ('salt:' + st.salt))
        ingest.backfill_pan_tokens(db)
        ingest.backfill_keys(db)

    # ------------------------------------------------------------ public check (privacy-preserving)
    def check(self, name, pincode='', folio=''):
        folios = clean_folios([folio]) if folio else []
        nm = ' '.join(name.split()) if name else ''
        if not folios:
            nm = clean_name(nm)
            if len(M.norm_tokens(nm)) < 2:
                raise ApiError('Enter at least your first and last name (initials are fine).')
        pin = clean_pin(pincode)
        res = M.find_matches(self.db, nm or 'X', pincode=pin, folios=folios, limit=60)
        ntok = max(len(M.norm_tokens(nm)), 1)
        likely = [r for r in res if r[1] in ('high', 'medium')]
        poss = [r for r in res if r[1] == 'low']
        out = []
        allr = likely + poss
        for r, conf, sc in allr[:self.st.free_companies]:  # the public preview is capped at the free-plan size
            out.append({'company': r['company'], 'fy': r['fy'], 'dtype': r['dtype'], 'name': M.mask_name_from_blob(r['blob'], ntok), 'folio': M.mask_folio(r['folio']),
                        'amount_band': M.amount_band(r['amount']), 'confidence': conf, 'deadline_est': r['iepf_due'], 'days_left': days_left(r['iepf_due'])})
        total = sum(r[0]['amount'] or 0 for r in likely)
        return {'likely': len(likely), 'possible': len(poss), 'results': out, 'more': max(len(allr) - len(out), 0), 'total_band': M.amount_band(total) if likely else None,
                'note': 'Names are masked. Create a free account to see full details for up to %d companies and get alerts.' % self.st.free_companies}

    # ------------------------------------------------------------ one-time-code helpers (used for mobile verification)
    def _hash(self, sid, ch, otp):
        return hashlib.sha256(('%s|%s|%s|%s' % (self.st.salt, sid, ch, otp)).encode()).hexdigest()

    def _otp(self):
        return '%06d' % secrets.randbelow(1000000)

    # ------------------------------------------------------------ matching
    def _sub_inputs(self, r):
        return r['name'], json.loads(r['aliases'] or '[]'), r['pincode'] or '', json.loads(r['folios'] or '[]')

    def match_subscriber(self, sid):
        r = self.db.one("SELECT * FROM subscribers WHERE id=? AND status='active'", (sid,))
        if not r:
            return 0
        name, aliases, pin, folios = self._sub_inputs(r)
        pan = self.vault.open(r['pan_enc']) if r['pan_enc'] else None
        if r['password_hash'] and not pan:  # accounts must register a PAN (in the profile) before anything is searched; old anonymous rows are exempt
            self.db.x('DELETE FROM matches WHERE sub_id=?', (sid,))
            return 0
        found4 = M.find_matches(self.db, name, aliases, pin, folios, limit=500, pan=pan or '', father=(r['father_name'] or ''), with_reason=True)
        found = [x[:3] for x in found4]
        why = {x[0]['id']: x[3] for x in found4}
        c = self.db.conn
        keep = [rec['id'] for rec, _, _ in found]
        if keep:  # matches that no longer fit the (possibly edited) profile go away
            c.execute('DELETE FROM matches WHERE sub_id=? AND rec_id NOT IN (%s)' % ','.join('?' * len(keep)), [sid] + keep)
        else:
            c.execute('DELETE FROM matches WHERE sub_id=?', (sid,))
        for rec, conf, sc in found:
            c.execute('INSERT INTO matches(sub_id,rec_id,conf,score,first_seen,via) VALUES(?,?,?,?,?,?) ON CONFLICT(sub_id,rec_id) DO UPDATE SET conf=excluded.conf, score=excluded.score, via=excluded.via',
                      (sid, rec['id'], conf, sc, now_iso(), why.get(rec['id'], '')))
        c.commit()
        self.allocate(sid)
        return len(found)

    def rematch_all(self):
        n = 0
        for r in self.db.q("SELECT id FROM subscribers WHERE status='active'"):
            n += self.match_subscriber(r['id'])
        self.db.meta_set('last_match_at', now_iso())
        return n

    def _match_rows(self, sid, where='1=1', args=()):
        return self.db.q('SELECT m.id mid, m.conf, m.score, m.notified, m.via, r.folio, r.amount, r.holding, r.name rname, r.addr raddr, r.blob, r.pincode, c.name company, c.id cid, l.fy, l.dtype, l.iepf_due, l.source_url, l.declared_on, r.id rid '
                         'FROM matches m JOIN records r ON r.id=m.rec_id JOIN companies c ON c.id=r.company_id JOIN lists l ON l.id=r.list_id '
                         'WHERE m.sub_id=? AND ' + where + ' ORDER BY r.amount DESC', (sid,) + tuple(args))

    # ------------------------------------------------------------ plan / company limit
    def plan_state(self, u):
        """What the user may use right now. Free = FREE_COMPANIES companies + email; Silver / Gold / Platinum come from settings.
        An expired membership drops back to Free. Rows paid for before tiers existed (no plan_tier) were "unlock everything" = Platinum."""
        until = u['plan_until']
        active = bool(until) and dt.date.fromisoformat(until) >= dt.date.today()
        key = (u['plan_tier'] or 'platinum') if active else 'free'
        if key != 'free' and key not in self.st.tiers:
            key = 'free'
        t = plans.tier(self.st, key)
        return {'active': active and key != 'free', 'tier': key, 'label': t['label'], 'until': until if active else None, 'expired_on': None if active else until,
                'companies': t['companies'], 'sms': t['sms'], 'whatsapp': t['whatsapp'], 'free_companies': self.st.free_companies}

    def _rows_in_plan(self, c, u, ps):
        """Company slots the user may see now: everything on an unlimited tier; else the earliest-granted slots up to the cap (free slots count first)."""
        if ps['active']:
            where, cap = '', ps['companies']
        else:
            where, cap = " AND kind='free'", self.st.free_companies
        return c.execute('SELECT company_id FROM unlocks WHERE user_id=?%s ORDER BY (kind=\'free\') DESC, at, rowid LIMIT ?' % where, (u['id'], cap)).fetchall()

    def allocate(self, sid):
        """Give the user the company slots their plan allows. Done once per company and never taken back (until the company stops matching),
        so what someone has seen stays visible. Order: likely matches before weak ones, then soonest IEPF deadline, then largest amount."""
        c = self.db.conn
        u = c.execute('SELECT * FROM subscribers WHERE id=?', (sid,)).fetchone()
        if not u:
            return
        ps = self.plan_state(u)
        have = {r[0] for r in c.execute('SELECT DISTINCT r.company_id FROM matches m JOIN records r ON r.id=m.rec_id WHERE m.sub_id=?', (sid,)).fetchall()}
        for row in c.execute('SELECT company_id FROM unlocks WHERE user_id=?', (sid,)).fetchall():
            if row[0] not in have:  # profile edited: this company no longer matches, release the slot
                c.execute('DELETE FROM unlocks WHERE user_id=? AND company_id=?', (sid, row[0]))
        if ps['active'] and ps['companies'] is None:
            c.commit()
            return
        cap = ps['companies'] if ps['active'] else self.st.free_companies
        used = c.execute('SELECT COUNT(*) FROM unlocks WHERE user_id=?%s' % ('' if ps['active'] else " AND kind='free'"), (sid,)).fetchone()[0]
        room = cap - used
        if room > 0:
            cand = c.execute(
                "SELECT r.company_id, MAX(CASE WHEN m.conf IN ('high','medium') THEN 1 ELSE 0 END) likely, MIN(COALESCE(l.iepf_due,'9999-12-31')) due, SUM(COALESCE(r.amount,0)) amt "
                'FROM matches m JOIN records r ON r.id=m.rec_id JOIN lists l ON l.id=r.list_id WHERE m.sub_id=? '
                'AND r.company_id NOT IN (SELECT company_id FROM unlocks WHERE user_id=?) GROUP BY r.company_id ORDER BY likely DESC, due ASC, amt DESC, r.company_id ASC LIMIT ?',
                (sid, sid, room)).fetchall()
            for row in cand:
                c.execute("INSERT OR IGNORE INTO unlocks(user_id,company_id,kind,at) VALUES(?,?,?,?)", (sid, row[0], 'plan' if ps['active'] else 'free', now_iso()))
        c.commit()

    allocate_free = allocate  # old name

    def visible_companies(self, u):
        """None = everything (unlimited tier); otherwise the set of company ids this user may see."""
        ps = self.plan_state(u)
        if ps['active'] and ps['companies'] is None:
            return None
        return {r[0] for r in self._rows_in_plan(self.db.conn, u, ps)}

    def _split(self, u, rows):
        vis = self.visible_companies(u)
        if vis is None:
            return list(rows), []
        return [m for m in rows if m['cid'] in vis], [m for m in rows if m['cid'] not in vis]

    # ------------------------------------------------------------ dashboard
    def summary(self, sid):
        rows = self._match_rows(sid)
        likely = [r for r in rows if r['conf'] in ('high', 'medium')]
        return {'likely': len(likely), 'possible': len(rows) - len(likely), 'amount': round(sum(r['amount'] or 0 for r in likely), 2)}

    def _item(self, m):
        """One dashboard row. Only strong (high-confidence) matches show the holder's name and address; weaker ones are masked because they may be someone else."""
        strong = m['conf'] == 'high'
        blob_toks = (m['blob'] or '').split()
        name = m['rname'] or ' '.join(blob_toks[:3])
        addr = m['raddr'] or ' '.join(blob_toks[3:])
        name = _PANRE.sub(lambda x: 'XXXXXX' + x.group(0)[-4:], name)  # a PAN printed inside a list row is never echoed back in full
        addr = _PANRE.sub(lambda x: 'XXXXXX' + x.group(0)[-4:], addr)
        return {'id': m['mid'], 'company': m['company'], 'fy': m['fy'], 'dtype': m['dtype'], 'folio': M.mask_folio(m['folio']), 'holding': m['holding'], 'amount': m['amount'], 'confidence': m['conf'],
                'deadline_est': m['iepf_due'], 'days_left': days_left(m['iepf_due']), 'source_url': m['source_url'], 'declared_on': m['declared_on'],
                'holder': name if strong else M.mask_name_from_blob(name, 6), 'address': addr if strong else '', 'pincode': m['pincode'] or '',
                'via': [M.VIA_LABEL.get(v, v) for v in (m['via'] or '').split(',') if v] if m['via'] else []}

    DUMMY_COS = ['Sample Steel Works Ltd', 'Demo Power Finance Ltd', 'Example Textiles Ltd', 'Test Pharma Industries Ltd', 'Mock Foods Ltd']

    def _dummy_search(self, u, modes):
        """LOCAL DEMO ONLY (DEV_MODE + DUMMY_DATA_EMAIL): replace this user's matches with 6-10 freshly generated sample rows, different on every search."""
        import random
        rnd, c, uid = random.Random(), self.db.conn, u['id']
        tag = 'dummy:%d:' % uid
        old = [r[0] for r in c.execute('SELECT id FROM lists WHERE file_hash LIKE ?', (tag + '%',)).fetchall()]
        for lid in old:
            c.execute('DELETE FROM rec_tok WHERE rec_id IN (SELECT id FROM records WHERE list_id=?)', (lid,))
            c.execute('DELETE FROM records WHERE list_id=?', (lid,))
            c.execute('DELETE FROM lists WHERE id=?', (lid,))
        c.execute('DELETE FROM matches WHERE sub_id=?', (uid,))
        first, last = (u['first_name'] or u['name'].split()[0]).upper(), (u['last_name'] or u['name'].split()[-1]).upper()
        pin = u['pincode'] or rnd.choice(['400001', '110001', '560001', '411001', '600001'])
        streets = ['MG ROAD', 'STATION ROAD', 'GANDHI NAGAR', 'LAKE VIEW COLONY', 'SUNRISE APARTMENTS', 'MARKET YARD']
        cities = ['MUMBAI', 'PUNE', 'DELHI', 'BENGALURU', 'CHENNAI', 'JAIPUR']
        cos = rnd.sample(self.DUMMY_COS, rnd.randint(2, 5))
        n = rnd.randint(6, 10)
        lists = {}
        for k, co in enumerate(cos):
            cid = self.db.one('SELECT id FROM companies WHERE name=?', (co,))
            cid = cid['id'] if cid else self.db.x('INSERT INTO companies(name) VALUES(?)', (co,)).lastrowid
            yr = rnd.randint(2019, 2026)
            declared = dt.date.today() - dt.timedelta(days=rnd.randint(200, 365 * 6 + 120))
            due = ingest.due_from_declared(declared)
            lid = c.execute('INSERT INTO lists(company_id,fy,dtype,source_url,declared_on,iepf_due,n_rows,total,ingested_at,file_hash,validation) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                            (cid, '%d-%02d' % (yr, (yr + 1) % 100), rnd.choice(['Final', 'Interim']), '', declared.isoformat(), due.isoformat(), 0, 0, now_iso(), '%s%d:%d' % (tag, k, rnd.getrandbits(40)), 'unverified')).lastrowid
            lists[co] = (lid, cid)
        kinds = ['pan', 'dp_client_id', 'dp_client_id', 'name+pin', 'name+pin', 'name', 'address', 'name']
        rows = 0
        for i in range(n):
            co = rnd.choice(cos)
            lid, cid = lists[co]
            via = rnd.choice(kinds)
            strong = via in ('pan', 'dp_client_id')
            folio = rnd.choice(['IN30', '1201', '1202', 'IN301']) + ''.join(str(rnd.randint(0, 9)) for _ in range(12))
            nm = ('%s %s' % (first, last)) if strong or via == 'name+pin' else rnd.choice(['%s %s %s' % (first, rnd.choice('ABKMRS'), last), '%s. %s' % (first[0], last), '%s %s' % (last, first)])
            addr = '%d %s %s' % (rnd.randint(1, 250), rnd.choice(streets), rnd.choice(cities))
            hold = rnd.choice([10, 25, 40, 55, 80, 120, 160, 250, 400, 1000])
            amt = round(hold * rnd.choice([1.5, 2.5, 4.25, 6.8, 9.0, 12.5, 21.0]), 2)
            conf = 'high' if strong else ('medium' if via == 'name+pin' else 'low')
            rid = c.execute('INSERT INTO records(list_id,company_id,folio,folio_key,blob,pincode,holding,amount,rowhash,dp_key,name,addr) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                            (lid, cid, folio, M.folio_key(folio), nm + ' ' + addr, pin, hold, amt, '%s%d:%d' % (tag, lid, rnd.getrandbits(48)), None, nm, addr)).lastrowid
            c.execute('INSERT INTO matches(sub_id,rec_id,conf,score,first_seen,via) VALUES(?,?,?,?,?,?)', (uid, rid, conf, 1.0 if strong else 0.8, now_iso(), via))
            rows += 1
        for co, (lid, cid) in lists.items():
            c.execute('UPDATE lists SET n_rows=(SELECT COUNT(*) FROM records WHERE list_id=?), total=(SELECT COALESCE(SUM(amount),0) FROM records WHERE list_id=?) WHERE id=?', (lid, lid, lid))
        c.commit()
        self.allocate(uid)
        out = self.me(u)
        out['searched'] = sorted(modes)
        out['found'] = rows
        out['sample'] = True
        return out

    def search(self, u, modes, wipe=True):
        """Dashboard search with the keys the user ticked. Results are stored as matches (so the claim flow can refer to them) and returned like me()."""
        modes = {x for x in (modes or []) if x in ('pan', 'ids', 'name', 'address')}
        if not modes:
            raise ApiError('Tick at least one thing to search with.')
        if self.st.dummy_data_email and (u['email'] or '').lower() == self.st.dummy_data_email:
            return self._dummy_search(u, modes)
        pan = self.vault.open(u['pan_enc']) if u['pan_enc'] else ''
        folios = json.loads(u['folios'] or '[]')
        if 'pan' in modes and not pan:
            raise ApiError('Add your PAN in your profile first, or untick PAN.')
        if 'ids' in modes and not folios:
            raise ApiError('Add your DP-Client ID or folio number in your profile first, or untick it.')
        if 'address' in modes and not ((u['address'] or u['city']) and u['pincode']):
            raise ApiError('Address search needs your address and PIN code in your profile. Add them or untick Address.')
        name, aliases, pin, _ = self._sub_inputs(u)
        found = M.search_matches(self.db, modes, name, aliases, pin, folios, pan, u['father_name'] or '', u['address'] or '', u['city'] or '', limit=500)
        c = self.db.conn
        keep = [r['id'] for r, _, _, _ in found]
        if wipe:
            if keep:
                c.execute('DELETE FROM matches WHERE sub_id=? AND rec_id NOT IN (%s)' % ','.join('?' * len(keep)), [u['id']] + keep)
            else:
                c.execute('DELETE FROM matches WHERE sub_id=?', (u['id'],))
        for rec, conf, sc, via in found:
            c.execute('INSERT INTO matches(sub_id,rec_id,conf,score,first_seen,via) VALUES(?,?,?,?,?,?) ON CONFLICT(sub_id,rec_id) DO UPDATE SET conf=excluded.conf, score=excluded.score, via=excluded.via',
                      (u['id'], rec['id'], conf, sc, now_iso(), ','.join(via)))
        c.commit()
        out = self.me(u)
        out['searched'] = sorted(modes)
        out['found'] = len(found)
        return out

    def me(self, u):
        """Dashboard data. Entries for companies outside the user's free slots / paid plan are returned only as a count and an amount band."""
        dummy = bool(self.st.dummy_data_email and (u['email'] or '').lower() == self.st.dummy_data_email)
        if dummy and not self.db.one("SELECT 1 FROM lists WHERE file_hash LIKE ?", ('dummy:%d:%%' % u['id'],)):
            return self._dummy_search(u, [])
        self.allocate(u['id'])
        rows = self._match_rows(u['id'])
        shown, locked = self._split(u, rows)
        items = []
        for m in shown:
            items.append(self._item(m))
        likely = [i for i in items if i['confidence'] in ('high', 'medium')]
        lk = [m for m in locked if m['conf'] in ('high', 'medium')]
        plan = self.plan_state(u)
        vis = self.visible_companies(u)
        used = len({m['cid'] for m in shown}) if vis is None else len(vis)
        needs_pan = bool(u['password_hash']) and not u['pan_hash']
        return {'sample': dummy, 'profile': {'name': u['name'], 'first_name': u['first_name'] or u['name'].split()[0], 'email': mask_email(u['email']), 'phone': mask_phone(u['phone']), 'since': u['verified_at'],
                            'pan_masked': ('XXXXXX' + u['pan_last4']) if u['pan_last4'] else None, 'ids': [M.mask_folio(f) for f in json.loads(u['folios'] or '[]')], 'has_address': bool((u['address'] or u['city']) and u['pincode'])},
                'plan': {**plan, 'used': used}, 'needs_pan': needs_pan, 'dp_count': len(json.loads(u['folios'] or '[]')),
                'likely': likely, 'possible': [i for i in items if i['confidence'] == 'low'], 'total_likely': round(sum(i['amount'] or 0 for i in likely), 2),
                'locked': {'companies': len({m['cid'] for m in locked}), 'entries': len(locked), 'likely_entries': len(lk),
                           'amount_band': M.amount_band(sum(m['amount'] or 0 for m in lk)) if lk else None}}

    def delete_user_data(self, sid):
        """Hard-delete everything about a user. Payment rows stay (tax / accounting records) but lose the link to a person."""
        c = self.db.conn
        c.execute('DELETE FROM claim_requests WHERE sub_id=?', (sid,))
        for t in ('matches', 'reminders', 'outbox'):
            c.execute('DELETE FROM %s WHERE sub_id=?' % t, (sid,))
        for t in ('sessions', 'auth_tokens', 'unlocks', 'consents'):
            c.execute('DELETE FROM %s WHERE user_id=?' % t, (sid,))
        c.execute('UPDATE payments SET user_id=NULL WHERE user_id=?', (sid,))
        c.execute('DELETE FROM subscribers WHERE id=?', (sid,))
        c.commit()

    # ------------------------------------------------------------ alerts
    def _link(self, r):
        # where a message sends the user: the dashboard (sign-in needed). Old anonymous subscribers have no account yet, so they go to sign-up.
        return '%s/%s' % (self.st.base_url, 'dashboard.html' if r['password_hash'] else 'signup.html')

    def _unsub_link(self, r):
        return '%s/unsubscribe.html?t=%s' % (self.st.base_url, r['token'])

    def _upgrade_note(self, r, locked):
        if not locked:
            return ''
        n, ps = len({m['cid'] for m in locked}), self.plan_state(r)
        return '\n\n%d more compan%s on your list %s hidden on your %s plan (%s). Upgrade: %s/upgrade.html\n' % (
            n, 'y' if n == 1 else 'ies', 'is' if n == 1 else 'are', ps['label'], '%d companies' % ps['companies'] if ps['companies'] else 'no limit', self.st.base_url)

    def _enqueue(self, r, kind, subject, email_body, short_body, vars):
        rows = []
        if r['ch_email']:
            rows.append(('email', r['email'], subject, email_body))
        ps = self.plan_state(r)
        if r['ch_sms'] and r['phone_verified_at'] and ps['sms']:  # SMS / WhatsApp only to a verified number, and only on plans that include them
            rows.append(('sms', r['phone'], None, short_body))
        if r['ch_wa'] and r['phone_verified_at'] and ps['whatsapp']:
            rows.append(('whatsapp', r['phone'], None, short_body + '\n\nStop these messages: ' + self._unsub_link(r)))
        for ch, to, sj, body in rows:
            self.db.conn.execute('INSERT INTO outbox(sub_id,channel,to_addr,kind,subject,body,vars,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                                 (r['id'], ch, to, kind, sj, body, json.dumps(vars), 'pending', now_iso()))
        self.db.conn.commit()

    def _lines(self, rows):
        out = []
        for m in rows[:8]:
            dl = days_left(m['iepf_due'])
            when = ' - est. moves to IEPF by %s' % dt.date.fromisoformat(m['iepf_due']).strftime('%d %b %Y') if m['iepf_due'] and dl is not None and dl >= 0 else ''
            out.append('  - %s: %s (%s %s), folio ...%s%s' % (m['company'], M.inr(m['amount']), m['dtype'] or 'Dividend', m['fy'] or '', (m['folio'] or '')[-4:], when))
        if len(rows) > 8:
            out.append('  ...and %d more' % (len(rows) - 8))
        return '\n'.join(out)

    CLAIM_STEPS = ('How to claim:\n1. Open your dashboard and note the company and folio.\n2. Write to the company / its registrar (RTA) with your folio number, PAN, ID proof and a cancelled cheque.\n'
                   '3. If the amount has already moved to the IEPF, file Form IEPF-5 on iepf.gov.in (free - no agent needed).')

    def process_alerts(self, only_sub=None):
        """Queue new-match alerts and deadline reminders. Returns number of messages queued (before channel fan-out)."""
        q = "SELECT * FROM subscribers WHERE status='active'" + (' AND id=%d' % int(only_sub) if only_sub else '')
        queued = 0
        brand = self.st.brand
        for r in self.db.q(q):
            sid = r['id']
            new = self._match_rows(sid, "m.notified=0 AND m.conf IN ('high','medium')")
            if new:
                shown, locked = self._split(r, new)
                total = sum(m['amount'] or 0 for m in new)
                link = self._link(r)
                subj = '%s: %d possible unclaimed dividend%s (%s) found for %s' % (brand, len(new), '' if len(new) == 1 else 's', M.inr(total), r['name'])
                listing = ('We found %d possible unclaimed dividend entr%s in company lists, worth about %s:\n\n%s' % (len(new), 'y' if len(new) == 1 else 'ies', M.inr(total), self._lines(shown))) if shown else \
                          ('We found %d possible unclaimed dividend entr%s in company lists, worth about %s.' % (len(new), 'y' if len(new) == 1 else 'ies', M.inr(total)))
                body = ('Hello %s,\n\n%s%s\n\nThese are matches on your name - please verify the folio before acting. See full details and your claim checklist:\n%s\n\n%s\n\n'
                        'Unclaimed dividends older than 7 years move to the government\'s IEPF - they can still be claimed, but the process is longer, so act early.\n\n'
                        'You get this because you have an account on %s. Turn alerts off any time: %s\n') % (
                    (r['first_name'] or r['name'].split()[0]).title(), listing, self._upgrade_note(r, locked), link, self.CLAIM_STEPS, self.st.base_url, self._unsub_link(r))
                short = '%s: %d possible unclaimed dividend%s worth Rs %s found for %s. Details & how to claim: %s' % (brand, len(new), '' if len(new) == 1 else 's', M.inr_plain(total), r['name'][:22], link)
                self._enqueue(r, 'alert', subj, body, short, {'name': r['name'][:22], 'count': len(new), 'amount': M.inr_plain(total), 'url': link})
                self.db.conn.execute('UPDATE matches SET notified=1 WHERE id IN (%s)' % ','.join(str(m['mid']) for m in new))
                self.db.conn.commit()
                queued += 1
            queued += self._reminders(r)
        return queued

    def _reminders(self, r):
        sid = r['id']
        due = []
        for m in self._split(r, self._match_rows(sid, "m.notified=1 AND m.conf IN ('high','medium') AND l.iepf_due IS NOT NULL"))[0]:
            dl = days_left(m['iepf_due'])
            if dl is None:
                continue
            stage = 0 if dl <= 0 else min([s for s in REMINDER_STAGES if dl <= s], default=None)
            if stage is None:
                continue
            bigger = [s for s in (0,) + REMINDER_STAGES if s >= stage]
            if self.db.one('SELECT 1 FROM reminders WHERE sub_id=? AND rec_id=? AND stage=?', (sid, m['rid'], stage)):
                continue
            for s in bigger:
                self.db.conn.execute('INSERT OR IGNORE INTO reminders(sub_id,rec_id,stage,sent_at) VALUES(?,?,?,?)', (sid, m['rid'], s, now_iso()))
            due.append((m, dl, stage))
        self.db.conn.commit()
        if not due:
            return 0
        total = sum(m['amount'] or 0 for m, _, _ in due)
        soon = min(dl for _, dl, _ in due)
        link = self._link(r)
        passed = soon <= 0
        if passed:
            subj = '%s: estimated IEPF transfer date has passed for %s of your unclaimed dividends' % (self.st.brand, M.inr(total))
        else:
            subj = '%s: about %d days left to claim %s of unclaimed dividends' % (self.st.brand, soon, M.inr(total))
        body = ('Hello %s,\n\n%s\n\n%s\n\n%s\n\nDetails: %s\n\nThe date is an estimate from the dividend declaration date - confirm it with the company\'s unclaimed-dividend notice.\nTurn alerts off any time: %s\n') % (
            (r['first_name'] or r['name'].split()[0]).title(),
            ('The estimated transfer date has passed, so these amounts may now be with the IEPF. They are still claimable via Form IEPF-5 (iepf.gov.in).' if passed else 'These amounts are estimated to move to the government IEPF in about %d days. Claiming from the company before that is faster.' % soon),
            self._lines([m for m, _, _ in due]), self.CLAIM_STEPS, link, self._unsub_link(r))
        short = ('%s: Rs %s unclaimed dividend may already be with IEPF - still claimable (Form IEPF-5). %s' % (self.st.brand, M.inr_plain(total), link)) if passed else \
                ('%s: ~%d days left to claim Rs %s unclaimed dividend before it moves to IEPF. %s' % (self.st.brand, soon, M.inr_plain(total), link))
        self._enqueue(r, 'reminder', subj, body, short, {'name': r['name'][:22], 'count': len(due), 'amount': M.inr_plain(total), 'url': link})
        return 1

    # ------------------------------------------------------------ outbox
    def dispatch_outbox(self, limit=100):
        sent = failed = 0
        for o in self.db.q("SELECT * FROM outbox WHERE status='pending' AND tries<5 ORDER BY id LIMIT ?", (limit,)):
            ok, err = self.n.send(o['channel'], o['to_addr'], o['body'], subject=o['subject'], kind=o['kind'], vars=json.loads(o['vars'] or '{}'))
            tries = o['tries'] + 1
            if ok:
                self.db.x("UPDATE outbox SET status='sent', sent_at=?, tries=?, err=NULL WHERE id=?", (now_iso(), tries, o['id']))
                sent += 1
            else:
                self.db.x("UPDATE outbox SET status=?, tries=?, err=? WHERE id=?", ('failed' if tries >= 5 else 'pending', tries, err, o['id']))
                failed += 1
        return {'sent': sent, 'failed': failed}

    def purge(self):
        cut = (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=48)).isoformat(timespec='seconds')
        for r in self.db.q("SELECT id FROM subscribers WHERE status='pending' AND created_at<?", (cut,)):  # never confirmed their email
            self.delete_user_data(r['id'])
        cut2 = (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=14)).isoformat(timespec='seconds')
        self.db.x("DELETE FROM outbox WHERE status='sent' AND sent_at<?", (cut2,))
        self.db.x('DELETE FROM sessions WHERE expires_at<?', (time.time(),))
        self.db.x('DELETE FROM auth_tokens WHERE exp<?', (time.time() - 86400,))

    def tick(self):
        """One worker cycle: re-match when new lists arrived, queue alerts/reminders, deliver, housekeeping."""
        li, lm = self.db.meta_get('last_ingest_at'), self.db.meta_get('last_match_at')
        if li and (not lm or li > lm):
            self.rematch_all()
        q = self.process_alerts()
        d = self.dispatch_outbox()
        self.purge()
        out = {'queued': q, **d}
        if self.st.crawl_enabled:
            try:
                import crawler
                out['crawled'] = len(crawler.crawl_due(self.db, os.path.dirname(os.path.abspath(self.st.db_path)), 10))
            except Exception as e:
                out['crawl_error'] = str(e)[:100]
        return out

    # ------------------------------------------------------------ public numbers / admin
    def public_stats(self):
        s = ingest.stats(self.db)
        return {'companies_covered': s['companies_covered'], 'records': s['records'], 'amount': s['amount'], 'last_ingest_at': s['last_ingest_at'],
                'subscribers': self.db.one("SELECT COUNT(*) n FROM subscribers WHERE status='active'")['n']}

    def coverage(self, term='', limit=100):
        """Honest coverage: for each company, the newest list we hold and how well it was read. Companies without a list are shown as not yet covered."""
        args, where = [], ''
        if term:
            where, args = 'WHERE c.name LIKE ? OR c.nse_symbol LIKE ? OR c.bse_code=? OR c.isin=?', ['%' + term + '%', term.upper() + '%', term, term.upper()]
        rows = self.db.q('SELECT c.id, c.name, c.nse_symbol, c.bse_code, c.isin, c.cin, '
                         '(SELECT MAX(l.ingested_at) FROM lists l WHERE l.company_id=c.id) last_list, '
                         '(SELECT COUNT(*) FROM lists l WHERE l.company_id=c.id) lists, '
                         '(SELECT l.validation FROM lists l WHERE l.company_id=c.id ORDER BY l.id DESC LIMIT 1) validation, '
                         '(SELECT t.last_checked FROM crawl_targets t WHERE t.company_id=c.id ORDER BY t.last_checked DESC LIMIT 1) last_checked '
                         'FROM companies c ' + where + ' ORDER BY (last_list IS NULL), c.name LIMIT ?', args + [min(max(int(limit), 1), 500)])
        total = self.db.one('SELECT COUNT(*) n FROM companies')['n']
        covered = self.db.one('SELECT COUNT(DISTINCT company_id) n FROM lists')['n']
        out = []
        for r in rows:
            d = dict(r)
            d['state'] = 'covered' if r['lists'] else 'not_yet'
            out.append(d)
        return {'companies_total': total, 'companies_covered': covered, 'companies': out,
                'official': [{'name': 'IEPF - search your shares', 'url': 'https://www.iepf.gov.in/IEPFWebSite/IEPF/home.html'},
                             {'name': 'MCA - investor services', 'url': 'https://www.mca.gov.in/content/mca/global/en/home.html'},
                             {'name': 'RBI UDGAM - bank deposits', 'url': 'https://udgam.rbi.org.in/'}],
                'note': 'We read the lists companies publish. A company marked "not yet" has not been checked, which does not mean you have nothing there.'}

    def admin_stats(self):
        s = ingest.stats(self.db)
        s['subscribers_active'] = self.db.one("SELECT COUNT(*) n FROM subscribers WHERE status='active'")['n']
        s['subscribers_pending'] = self.db.one("SELECT COUNT(*) n FROM subscribers WHERE status='pending'")['n']
        import registry
        s['registry'] = registry.registry_stats(self.db)
        s['sources'] = {r['status']: r['n'] for r in self.db.q('SELECT status, COUNT(*) n FROM source_docs GROUP BY status')}
        s['accounts'] = self.db.one('SELECT COUNT(*) n FROM subscribers WHERE password_hash IS NOT NULL')['n']
        s['paid_plans_active'] = self.db.one('SELECT COUNT(*) n FROM subscribers WHERE plan_until>=?', (dt.date.today().isoformat(),))['n']
        s['paid_by_tier'] = {r['t']: r['n'] for r in self.db.q("SELECT COALESCE(plan_tier,'platinum') t, COUNT(*) n FROM subscribers WHERE plan_until>=? GROUP BY t", (dt.date.today().isoformat(),))}
        s['payments_pending_review'] = self.db.one("SELECT COUNT(*) n FROM payments WHERE status='pending_review'")['n']
        s['revenue_inr'] = round((self.db.one("SELECT COALESCE(SUM(amount_paise),0) n FROM payments WHERE status='paid'")['n'] or 0) / 100, 2)
        s['matches'] = self.db.one('SELECT COUNT(*) n FROM matches')['n']
        s['outbox'] = {r['status']: r['n'] for r in self.db.q('SELECT status, COUNT(*) n FROM outbox GROUP BY status')}
        s['recent_lists'] = [dict(r) for r in self.db.q('SELECT l.id, c.name company, c.id cid, l.fy, l.dtype, l.n_rows, l.total, l.iepf_due, l.ingested_at FROM lists l JOIN companies c ON c.id=l.company_id ORDER BY l.id DESC LIMIT 15')]
        s['failed_messages'] = [dict(r) for r in self.db.q("SELECT id, channel, kind, err, tries FROM outbox WHERE status!='sent' AND err IS NOT NULL ORDER BY id DESC LIMIT 10")]
        return s
