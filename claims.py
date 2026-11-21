"""Optional paid-help flow: expert panel (CS / CA / CMA / advocates) and customer claim-assistance requests.
Signed-in users only; they can claim only entries unlocked for them. The expert fee is NOT collected here and no documents are stored. The admin verifies experts' membership numbers by hand
(ICSI / ICAI / ICMAI / Bar Council directories), sends quotes, and assigns requests."""
import datetime as dt
import json
import re

from service import ApiError, clean_name, norm_email, norm_phone, mask_email

PROFESSIONS = ('Company Secretary', 'Chartered Accountant', 'Cost Accountant', 'Advocate', 'Other')
EXPERT_STATUS = ('pending', 'verified', 'suspended')
CLAIM_STATUS = ('new', 'quoted', 'accepted', 'assigned', 'in_progress', 'completed', 'cancelled')
OPEN = ('new', 'quoted', 'accepted', 'assigned', 'in_progress')
STATUS_TEXT = {'new': 'Received - we are reviewing it', 'quoted': 'Quote ready - please accept or decline', 'accepted': 'Quote accepted - assigning an expert',
               'assigned': 'Expert assigned', 'in_progress': 'In progress', 'completed': 'Completed', 'cancelled': 'Cancelled'}


def now():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')


def _txt(s, n, field, req=True):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    if req and not s:
        raise ApiError('%s is required.' % field)
    return s[:n]


class Claims:
    def __init__(self, svc):
        self.svc, self.db, self.st = svc, svc.db, svc.st

    # ---------------------------------------------------------------- experts
    def register_expert(self, p):
        if p.get('consent') is not True:
            raise ApiError('Please accept the panel terms.')
        prof = p.get('profession')
        if prof not in PROFESSIONS:
            raise ApiError('Choose your profession.')
        name, email, phone = clean_name(p.get('name')), norm_email(p.get('email')), norm_phone(p.get('phone'))
        mno = _txt(p.get('membership_no'), 30, 'Membership / enrolment number')
        city, langs = _txt(p.get('city'), 60, 'City'), _txt(p.get('languages'), 80, 'Languages', False)
        if self.db.one('SELECT id FROM experts WHERE email=?', (email,)):
            raise ApiError('This email is already registered. We will contact you after verification.', 409)
        self.db.x('INSERT INTO experts(name,profession,membership_no,city,email,phone,languages,status,consent_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (name, prof, mno, city, email, phone, langs, 'pending', now(), now()))
        return {'ok': True}

    def public_panel(self):
        rows = self.db.q("SELECT name, profession, membership_no, city, languages FROM experts WHERE status='verified' ORDER BY name")
        return [dict(r) for r in rows]

    def admin_experts(self):
        return [dict(r) for r in self.db.q('SELECT * FROM experts ORDER BY (status="pending") DESC, id DESC LIMIT 200')]

    def admin_set_expert(self, eid, status, note=''):
        if status not in EXPERT_STATUS:
            raise ApiError('Bad status.')
        if not self.db.one('SELECT id FROM experts WHERE id=?', (eid,)):
            raise ApiError('Expert not found.', 404)
        self.db.x('UPDATE experts SET status=?, admin_note=?, verified_at=? WHERE id=?', (status, _txt(note, 300, '', False), now() if status == 'verified' else None, eid))
        return {'ok': True}

    # ---------------------------------------------------------------- customer side
    def create(self, r, p):
        if p.get('consent') is not True:
            raise ApiError('Please agree to share these details with the assigned expert.')
        ids = [int(i) for i in (p.get('match_ids') or [])][:20]
        if not ids:
            raise ApiError('Select at least one entry you want help with.')
        if self.db.one('SELECT COUNT(*) n FROM claim_requests WHERE sub_id=? AND status IN (%s)' % ','.join('?' * len(OPEN)), (r['id'],) + OPEN)['n'] >= 5:
            raise ApiError('You already have several open requests. Please wait for them to progress.', 429)
        rows = self.svc._match_rows(r['id'], 'm.id IN (%s)' % ','.join('?' * len(ids)), ids)
        rows = self.svc._split(r, rows)[0]  # only entries this user can actually see (free slots / paid plan)
        if len(rows) != len(set(ids)):
            raise ApiError('Some selected entries were not found, or are locked on the free plan.')
        items = [{'company': m['company'], 'fy': m['fy'], 'dtype': m['dtype'], 'folio': m['folio'], 'amount': m['amount'], 'holding': m['holding'], 'deadline_est': m['iepf_due']} for m in rows]
        cur = self.db.x('INSERT INTO claim_requests(sub_id,items,notes,status,consent_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                        (r['id'], json.dumps(items), _txt(p.get('notes'), 500, '', False), 'new', now(), now(), now()))
        self._tell(r, 'We received your expert-help request #%d' % cur.lastrowid,
                   'Hello %s,\n\nWe received your request for help claiming %d entr%s. An independent registered professional from our panel will review it. You will receive a written fee quote first - nothing starts and nothing is charged until you accept it.\n\n'
                   'Track it here: %s\n\nNever share OTPs or bank passwords with anyone.' % ((r['first_name'] or r['name'].split()[0]).title(), len(items), 'y' if len(items) == 1 else 'ies', self.svc._link(r)),
                   '%s: expert-help request #%d received. Track: %s' % (self.st.brand, cur.lastrowid, self.svc._link(r)))
        return {'ok': True, 'id': cur.lastrowid}

    def mine(self, sid):
        out = []
        for c in self.db.q('SELECT * FROM claim_requests WHERE sub_id=? ORDER BY id DESC', (sid,)):
            ex = self.db.one('SELECT name, profession, membership_no, city FROM experts WHERE id=?', (c['expert_id'],)) if c['expert_id'] else None
            out.append({'id': c['id'], 'status': c['status'], 'status_text': STATUS_TEXT[c['status']], 'count': len(json.loads(c['items'])), 'created_at': c['created_at'],
                        'quote_amount': c['quote_amount'], 'quote_note': c['quote_note'], 'expert': dict(ex) if ex else None})
        return out

    def respond(self, r, cid, accept):
        c = self.db.one("SELECT * FROM claim_requests WHERE id=? AND sub_id=?", (cid, r['id']))
        if not c:
            raise ApiError('Request not found.', 404)
        if accept and c['status'] != 'quoted':
            raise ApiError('There is no quote to accept right now.')
        if not accept and c['status'] not in OPEN:
            raise ApiError('This request is already closed.')
        new = 'accepted' if accept else 'cancelled'
        self.db.x('UPDATE claim_requests SET status=?, updated_at=? WHERE id=?', (new, now(), cid))
        return {'ok': True, 'status': new}

    # ---------------------------------------------------------------- admin
    def admin_list(self):
        out = []
        for c in self.db.q('SELECT c.*, s.name sname, s.email semail, s.phone sphone FROM claim_requests c JOIN subscribers s ON s.id=c.sub_id ORDER BY (c.status IN ("completed","cancelled")), c.id DESC LIMIT 200'):
            d = dict(c)
            d['items'] = json.loads(c['items'])
            out.append(d)
        return out

    def admin_update(self, cid, p):
        c = self.db.one('SELECT * FROM claim_requests WHERE id=?', (cid,))
        if not c:
            raise ApiError('Request not found.', 404)
        r = self.db.one('SELECT * FROM subscribers WHERE id=?', (c['sub_id'],))
        status, eid = p.get('status', c['status']), p.get('expert_id', c['expert_id'])
        if status not in CLAIM_STATUS:
            raise ApiError('Bad status.')
        quote, qn = c['quote_amount'], c['quote_note']
        if p.get('quote_amount') not in (None, ''):
            try:
                quote = round(float(p['quote_amount']), 2)
            except ValueError:
                raise ApiError('Quote must be a number.')
            if quote < 0:
                raise ApiError('Quote must be a number.')
            qn = _txt(p.get('quote_note'), 300, '', False)
            if status in ('new', 'quoted'):
                status = 'quoted'
        if status in ('assigned', 'in_progress', 'completed'):
            ex = self.db.one("SELECT * FROM experts WHERE id=? AND status='verified'", (eid,)) if eid else None
            if not ex:
                raise ApiError('Assign a verified expert first.')
        self.db.x('UPDATE claim_requests SET status=?, expert_id=?, quote_amount=?, quote_note=?, updated_at=? WHERE id=?', (status, eid or None, quote, qn, now(), cid))
        if r and status != c['status']:
            link = self.svc._link(r)
            msg = {'quoted': 'Your fee quote is ready: %s%s. Open your dashboard to accept or decline: %s' % ('Rs ' + str(quote) if quote is not None else '', (' - ' + qn) if qn else '', link),
                   'assigned': 'An expert has been assigned to your request. Details are on your dashboard: %s' % link,
                   'in_progress': 'Your claim work has started. Status: %s' % link, 'completed': 'Your request is marked completed. Details: %s' % link}.get(status)
            if msg:
                self._tell(r, '%s: update on your request #%d' % (self.st.brand, cid), 'Hello %s,\n\n%s\n' % ((r['first_name'] or r['name'].split()[0]).title(), msg), '%s: %s' % (self.st.brand, msg[:120]))
        return {'ok': True, 'status': status}

    def _tell(self, r, subject, body, short):
        # email only: DLT / WhatsApp template providers cannot carry free-text status updates
        self.db.x('INSERT INTO outbox(sub_id,channel,to_addr,kind,subject,body,vars,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                  (r['id'], 'email', r['email'], 'claim', subject, body, '{}', 'pending', now()))
