"""Contact / support requests, feedback, and the admin tools to manage them, users and records."""
import datetime as dt
import re
import secrets

from service import ApiError

KINDS = ('contact', 'feedback', 'story')
TOPICS = ('Account or sign-in', 'Payment or plan', 'A match looks wrong', 'Claiming my dividend', 'Data or coverage', 'Partnership or press', 'Something else')
FEEDBACK_TOPICS = ('Idea or feature', 'Something is not working', 'Praise', 'Something else')
STATUSES = ('new', 'open', 'resolved', 'spam')
EMAIL = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$')


def now():
    return dt.datetime.now().isoformat(timespec='seconds')


def _clip(v, n):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(v or '')).strip()[:n]


class Support:
    def __init__(self, svc):
        self.svc, self.db, self.st = svc, svc.db, svc.st

    def site_info(self):
        s = self.st
        wa = re.sub(r'\D', '', s.support_whatsapp or '')
        return {'brand': s.brand, 'email': s.support_email, 'phone': s.support_phone, 'whatsapp': wa, 'hours': s.support_hours,
                'address': s.office_address, 'topics': list(TOPICS), 'feedback_topics': list(FEEDBACK_TOPICS)}

    def submit(self, kind, d, user=None):
        if kind not in KINDS:
            raise ApiError('Unknown form.')
        if _clip(d.get('website'), 50):  # honeypot field: real people never fill it
            return {'ref': 'DK-0000', 'received': True}
        name = _clip(d.get('name') or (user['name'] if user else ''), 80)
        email = _clip(d.get('email') or (user['email'] if user else ''), 254).lower()
        phone = re.sub(r'[^\d+ ]', '', _clip(d.get('phone'), 20))
        body = _clip(d.get('message'), 4000)
        topic = _clip(d.get('topic'), 60)
        if len(name) < 2:
            raise ApiError('Please tell us your name.')
        if not EMAIL.match(email):
            raise ApiError('Please enter a valid email address so we can reply.')
        if len(body) < 10:
            raise ApiError('Please write a little more (at least 10 characters).')
        if kind == 'story':
            topic = 'Customer story'
        elif topic not in (TOPICS if kind == 'contact' else FEEDBACK_TOPICS):
            topic = 'Something else'
        city = _clip(d.get('city'), 60)
        recovered = _clip(d.get('recovered'), 40)
        consent = 1 if d.get('consent') in (True, 1, '1', 'true', 'yes') else 0
        if kind == 'story' and not consent:
            raise ApiError('Please tick the box to let us show your story, or send it as feedback instead.')
        if kind == 'story' and len(body) < 40:
            raise ApiError('Please tell your story in a few more words (at least 40 characters).')
        rating = None
        if kind in ('feedback', 'story') and d.get('rating') not in (None, ''):
            try:
                rating = int(d.get('rating'))
            except (TypeError, ValueError):
                raise ApiError('Rating must be 1 to 5.')
            if not 1 <= rating <= 5:
                raise ApiError('Rating must be 1 to 5.')
        if self.db.one("SELECT COUNT(*) n FROM messages WHERE email=? AND created_at>?", (email, (dt.datetime.now() - dt.timedelta(hours=1)).isoformat(timespec='seconds')))['n'] >= 5:
            raise ApiError('You have sent several messages in the last hour. Please wait a little before sending another.', 429)
        ref = 'DK-%s' % secrets.token_hex(3).upper()
        self.db.x('INSERT INTO messages(kind,ref,user_id,name,email,phone,topic,rating,body,status,created_at,updated_at,city,recovered,consent_publish,published) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)',
                  (kind, ref, user['id'] if user else None, name, email, phone, topic, rating, body, 'new', now(), now(), city, recovered, consent))
        return {'ref': ref, 'received': True}

    def testimonials(self):
        """Public: only stories the owner has approved, shown as first name + last initial. Nothing is ever invented."""
        rows = self.db.q("SELECT name, city, rating, body, recovered FROM messages WHERE kind='story' AND published=1 AND consent_publish=1 AND status!='spam' ORDER BY updated_at DESC LIMIT 30")
        out = []
        for r in rows:
            parts = (r['name'] or '').split()
            shown = parts[0] + (' %s.' % parts[-1][0].upper() if len(parts) > 1 else '')
            out.append({'name': shown, 'city': r['city'] or '', 'rating': r['rating'], 'quote': r['body'], 'recovered': r['recovered'] or ''})
        return {'stories': out}

    def admin_story_publish(self, mid, publish):
        m = self.db.one('SELECT kind, consent_publish FROM messages WHERE id=?', (mid,))
        if not m or m['kind'] != 'story':
            raise ApiError('Story not found.', 404)
        if publish and not m['consent_publish']:
            raise ApiError('This person did not give permission to publish.')
        self.db.x('UPDATE messages SET published=?, updated_at=? WHERE id=?', (1 if publish else 0, now(), mid))
        return {'ok': True}

    # ------------------------------------------------------------------ admin
    def admin_messages(self, status='', kind=''):
        w, a = [], []
        if status in STATUSES:
            w.append('status=?'); a.append(status)
        if kind in KINDS:
            w.append('kind=?'); a.append(kind)
        rows = self.db.q('SELECT * FROM messages %s ORDER BY id DESC LIMIT 200' % ('WHERE ' + ' AND '.join(w) if w else ''), a)
        counts = {r['status']: r['n'] for r in self.db.q('SELECT status, COUNT(*) n FROM messages GROUP BY status')}
        avg = self.db.one("SELECT AVG(rating) a, COUNT(rating) n FROM messages WHERE kind='feedback' AND rating IS NOT NULL")
        return {'messages': [dict(r) for r in rows], 'counts': counts, 'avg_rating': round(avg['a'], 2) if avg['a'] else None, 'ratings': avg['n']}

    def admin_message_update(self, mid, status, note):
        if status not in STATUSES:
            raise ApiError('Unknown status.')
        if not self.db.one('SELECT 1 FROM messages WHERE id=?', (mid,)):
            raise ApiError('Message not found.', 404)
        self.db.x('UPDATE messages SET status=?, admin_note=?, updated_at=? WHERE id=?', (status, _clip(note, 1000), now(), mid))
        return {'ok': True}

    def admin_users(self, term=''):
        term = _clip(term, 60)
        like = '%' + term + '%'
        rows = self.db.q("SELECT id, name, email, phone, status, plan_tier, plan_until, created_at, email_verified_at FROM subscribers "
                         "WHERE password_hash IS NOT NULL AND (?='' OR name LIKE ? OR email LIKE ? OR phone LIKE ?) ORDER BY id DESC LIMIT 100", (term, like, like, like))
        return {'users': [dict(r) for r in rows]}

    def admin_user_delete(self, uid):
        if not self.db.one('SELECT 1 FROM subscribers WHERE id=?', (uid,)):
            raise ApiError('User not found.', 404)
        self.svc.delete_user_data(uid)
        return {'ok': True}

    def admin_lists(self, term=''):
        like = '%' + _clip(term, 60) + '%'
        rows = self.db.q('SELECT l.id, c.name company, l.fy, l.dtype, l.n_rows, l.total, l.declared_on, l.iepf_due, l.ingested_at FROM lists l JOIN companies c ON c.id=l.company_id '
                         'WHERE c.name LIKE ? ORDER BY l.id DESC LIMIT 100', (like,))
        return {'lists': [dict(r) for r in rows]}

    def admin_list_delete(self, lid):
        if not self.db.one('SELECT 1 FROM lists WHERE id=?', (lid,)):
            raise ApiError('List not found.', 404)
        ids = [r['id'] for r in self.db.q('SELECT id FROM records WHERE list_id=?', (lid,))]
        for i in range(0, len(ids), 500):
            ch = ids[i:i + 500]
            m = ','.join('?' * len(ch))
            self.db.x('DELETE FROM rec_tok WHERE rec_id IN (%s)' % m, ch)
            self.db.x('DELETE FROM matches WHERE rec_id IN (%s)' % m, ch)
        self.db.x('DELETE FROM records WHERE list_id=?', (lid,))
        self.db.x('DELETE FROM lists WHERE id=?', (lid,))
        return {'ok': True, 'records_removed': len(ids)}

    def admin_records(self, term='', company=''):
        term, company = _clip(term, 60).lower(), _clip(company, 60)
        w, a = [], []
        if company:
            w.append('c.name LIKE ?'); a.append('%' + company + '%')
        if term:
            w.append('(LOWER(r.blob) LIKE ? OR r.folio_key LIKE ?)'); a += ['%' + term + '%', '%' + re.sub(r'[^a-z0-9]', '', term) + '%']
        rows = self.db.q('SELECT r.id, c.name company, l.fy, r.folio, r.holding, r.amount, r.pincode, r.blob FROM records r JOIN companies c ON c.id=r.company_id JOIN lists l ON l.id=r.list_id '
                         '%s ORDER BY r.id DESC LIMIT 100' % ('WHERE ' + ' AND '.join(w) if w else ''), a)
        out = []
        for r in rows:
            d = dict(r)
            d['blob'] = (d['blob'] or '')[:160]
            out.append(d)
        return {'records': out}

    def admin_record_delete(self, rid):
        if not self.db.one('SELECT 1 FROM records WHERE id=?', (rid,)):
            raise ApiError('Record not found.', 404)
        for t, col in (('rec_tok', 'rec_id'), ('matches', 'rec_id'), ('records', 'id')):
            self.db.x('DELETE FROM %s WHERE %s=?' % (t, col), (rid,))
        return {'ok': True}
