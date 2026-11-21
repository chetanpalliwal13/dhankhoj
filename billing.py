"""Memberships: Silver / Gold / Platinum, each bought monthly (30 days) or yearly (365 days, discounted). The Free plan needs no payment.

Three ways to pay, all ending in `mark_paid()` which grants the purchased period exactly once per payment:
  * razorpay  - Razorpay Checkout (UPI, cards, netbanking, wallets). Server creates the order, the browser pays, and the result is confirmed
                two ways: the signed checkout callback AND Razorpay's signed webhook (covers a closed browser tab).
  * upi       - direct UPI to your own VPA: customer pays in any UPI app and submits the 12-digit UTR; an admin approves it in /admin.html
                after seeing the credit in the bank statement. Nothing is granted automatically.
  * mock      - fake gateway for local testing; only works with DEV_MODE=1.
The price always comes from server settings, never from the browser.
"""
import datetime as dt
import hashlib
import hmac
import json
import re
import sqlite3
import sys
import urllib.parse

from notify import _http
import plans
from service import ApiError, now_iso, norm_email

UTR_RE = re.compile(r'^\d{12}$')


class Billing:
    def __init__(self, svc):
        self.svc, self.db, self.st, self.n = svc, svc.db, svc.st, svc.n

    # -------------------------------------------------------------- configuration
    def provider(self):
        s = self.st
        if s.pay_provider == 'razorpay' and s.razorpay_key_id and s.razorpay_key_secret:
            return 'razorpay'
        if s.pay_provider == 'mock' and s.dev_mode:
            return 'mock'
        return None

    def upi_on(self):
        return bool(self.st.upi_vpa)

    def _pick(self, tier, period):
        tier, period = str(tier or '').lower(), str(period or '').lower()
        if not plans.valid(self.st, tier, period):
            raise ApiError('Please choose a plan (Silver, Gold or Platinum) and monthly or yearly billing.')
        return tier, period

    def carry_days(self, u, new_tier):
        """Switching tier mid-membership: the days left are converted at the ratio of the monthly prices, so nothing already paid is lost."""
        if not u['plan_until']:
            return 0
        left = (dt.date.fromisoformat(u['plan_until']) - dt.date.today()).days
        cur = u['plan_tier'] or 'platinum'
        if left <= 0 or cur not in self.st.tiers:
            return 0
        if cur == new_tier:
            return left
        return int(left * self.st.tiers[cur]['monthly'] // self.st.tiers[new_tier]['monthly'])

    def plan_info(self, u=None):
        s = self.st
        out = {'tiers': plans.public(s), 'free': {**plans.free(s), 'features': ['%d companies shown in full' % s.free_companies, 'Email alerts', 'Up to %d demat / folio IDs plus PAN matching' % s.max_dp_ids]},
               'periods': plans.PERIODS, 'yearly_discount': s.yearly_discount, 'gst_percent': s.gst_percent, 'free_companies': s.free_companies, 'max_dp_ids': s.max_dp_ids,
               'gateway': self.provider(), 'upi': self.upi_on(), 'upi_vpa': s.upi_vpa if self.upi_on() else None, 'upi_payee': s.upi_payee, 'support_email': s.support_email}
        if u is not None:
            ps = self.svc.plan_state(u)
            out['current'] = {'tier': ps['tier'], 'label': ps['label'], 'active': ps['active'], 'until': ps['until'], 'days_left': (dt.date.fromisoformat(ps['until']) - dt.date.today()).days if ps['until'] else 0}
            out['carry'] = {k: self.carry_days(u, k) for k in s.tiers} if ps['active'] else {}
        return out

    def _new(self, u, provider, tier, period, order_id=None):
        cur = self.db.x('INSERT INTO payments(user_id,billed_name,provider,amount_paise,currency,status,provider_order_id,plan_days,tier,period,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (u['id'], u['name'], provider, plans.paise(self.st, tier, period), 'INR', 'created', order_id, plans.PERIODS[period], tier, period, now_iso()))
        return cur.lastrowid

    def _own(self, u, pid):
        p = self.db.one('SELECT * FROM payments WHERE id=? AND user_id=?', (pid, u['id']))
        if not p:
            raise ApiError('Payment not found.', 404)
        return p

    # -------------------------------------------------------------- gateway (Razorpay / mock)
    def create_order(self, u, tier, period):
        tier, period = self._pick(tier, period)
        prov = self.provider()
        if not prov:
            raise ApiError('Online payment is not available right now.', 503)
        amt = plans.paise(self.st, tier, period)
        if amt < 100:
            raise ApiError('Payment is not set up correctly (price).', 503)
        if prov == 'mock':
            pid = self._new(u, 'mock', tier, period)
            self.db.x('UPDATE payments SET provider_order_id=? WHERE id=?', ('mock_order_%d' % pid, pid))
            return {'provider': 'mock', 'payment_id': pid, 'amount_paise': amt}
        pid = self._new(u, 'razorpay', tier, period)
        try:
            _, body = _http('%s/v1/orders' % self.st.razorpay_base, js={'amount': amt, 'currency': 'INR', 'receipt': 'DK-%d' % pid, 'notes': {'payment_id': str(pid), 'user_id': str(u['id'])}},
                            basic=(self.st.razorpay_key_id, self.st.razorpay_key_secret))
            oid = json.loads(body)['id']
        except Exception as e:
            sys.stderr.write('razorpay order error: %r\n' % (e,))
            self.db.x("UPDATE payments SET status='failed', note='order creation failed' WHERE id=?", (pid,))
            raise ApiError('The payment service did not respond. Please try again in a minute.', 502)
        self.db.x('UPDATE payments SET provider_order_id=? WHERE id=?', (oid, pid))
        return {'provider': 'razorpay', 'payment_id': pid, 'order_id': oid, 'key_id': self.st.razorpay_key_id, 'amount_paise': amt, 'currency': 'INR',
                'name': self.st.brand, 'description': plans.label(self.st, tier, period), 'prefill': {'name': u['name'], 'email': u['email'], 'contact': u['phone']}}

    def confirm_checkout(self, u, d):
        """Browser callback after Razorpay Checkout succeeds: verify the signature with our secret before granting anything."""
        if self.provider() != 'razorpay':
            raise ApiError('Online payment is not available right now.', 503)
        oid, pay_id, sig = str(d.get('razorpay_order_id', '')), str(d.get('razorpay_payment_id', '')), str(d.get('razorpay_signature', ''))
        p = self.db.one('SELECT * FROM payments WHERE provider_order_id=? AND user_id=? AND provider=?', (oid, u['id'], 'razorpay'))
        if not p:
            raise ApiError('Payment not found.', 404)
        want = hmac.new(self.st.razorpay_key_secret.encode(), ('%s|%s' % (oid, pay_id)).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want, sig):
            raise ApiError('We could not verify this payment. If money was deducted, it will be matched automatically or contact us with your payment ID.', 400)
        self.mark_paid(p['id'], pay_id)
        return {'paid': True}

    def webhook_razorpay(self, raw, signature):
        """Razorpay -> us, signed with RAZORPAY_WEBHOOK_SECRET. Idempotent, so Razorpay's retries are harmless."""
        sec = self.st.razorpay_webhook_secret
        if not sec or not hmac.compare_digest(hmac.new(sec.encode(), raw, hashlib.sha256).hexdigest(), signature or ''):
            raise ApiError('Bad signature.', 400)
        try:
            ev = json.loads(raw)
            if ev.get('event') not in ('payment.captured', 'order.paid'):
                return {'ignored': True}
            pay = (ev.get('payload') or {}).get('payment', {}).get('entity', {})
            oid, pay_id, amount = pay.get('order_id'), pay.get('id'), pay.get('amount')
        except (ValueError, AttributeError):
            raise ApiError('Bad payload.', 400)
        p = self.db.one('SELECT * FROM payments WHERE provider_order_id=? AND provider=?', (oid, 'razorpay')) if oid else None
        if not p:
            return {'ignored': True}  # not one of ours: answer 200 so Razorpay stops retrying
        if amount != p['amount_paise']:
            sys.stderr.write('razorpay webhook: amount mismatch for payment %s\n' % p['id'])
            return {'ignored': True}
        self.mark_paid(p['id'], pay_id, pay.get('method'))
        return {'ok': True}

    def mock_confirm(self, u, pid):
        if self.provider() != 'mock':
            raise ApiError('Not available.', 404)
        p = self._own(u, pid)
        self.mark_paid(p['id'], 'mock_pay_%d' % pid, 'mock')
        return {'paid': True}

    # -------------------------------------------------------------- direct UPI (manual approval)
    def upi_start(self, u, tier, period):
        tier, period = self._pick(tier, period)
        if not self.upi_on():
            raise ApiError('Direct UPI payment is not available.', 503)
        p = self.db.one("SELECT * FROM payments WHERE user_id=? AND provider='upi' AND status='created' AND created_at>? ORDER BY id DESC",
                        (u['id'], (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=24)).isoformat(timespec='seconds')))
        if p:  # an unpaid UPI attempt from the last day is re-used, switched to the plan chosen now
            self.db.x('UPDATE payments SET tier=?, period=?, plan_days=?, amount_paise=? WHERE id=?', (tier, period, plans.PERIODS[period], plans.paise(self.st, tier, period), p['id']))
            pid = p['id']
        else:
            pid = self._new(u, 'upi', tier, period)
        ref = 'DK%d' % pid
        amt = '%.2f' % (plans.paise(self.st, tier, period) / 100)
        q = urllib.parse.urlencode({'pa': self.st.upi_vpa, 'pn': self.st.upi_payee, 'am': amt, 'cu': 'INR', 'tn': ref}, quote_via=urllib.parse.quote)
        return {'payment_id': pid, 'ref': ref, 'vpa': self.st.upi_vpa, 'payee': self.st.upi_payee, 'amount': amt, 'link': 'upi://pay?' + q}

    def upi_submit(self, u, pid, utr):
        p = self._own(u, pid)
        if p['provider'] != 'upi' or p['status'] != 'created':
            raise ApiError('This payment cannot take a reference number any more.')
        utr = re.sub(r'\s+', '', str(utr or ''))
        if not UTR_RE.match(utr):
            raise ApiError('Enter the 12-digit UPI reference number (UTR) from your payment app.')
        try:
            self.db.x("UPDATE payments SET utr=?, status='pending_review', method='upi' WHERE id=? AND status='created'", (utr, pid))
        except sqlite3.IntegrityError:
            raise ApiError('That reference number has already been submitted. Contact us if you think this is a mistake.', 409)
        self.n.send('email', u['email'], 'Hello %s,\n\nWe received your UPI payment reference %s for %s. We match it against our bank statement and activate your plan, usually within a few working hours. '
                    'You will get a confirmation email.\n' % ((u['first_name'] or u['name']).title(), utr, self._plan_label(p)), subject='%s: payment reference received' % self.st.brand, kind='account')
        return {'status': 'pending_review'}

    # -------------------------------------------------------------- granting
    def _plan_label(self, p):
        t = p['tier'] if p['tier'] in self.st.tiers else 'platinum'  # payments made before tiers existed bought "unlock everything"
        return plans.label(self.st, t, p['period'])

    def mark_paid(self, pid, provider_payment_id=None, method=None):
        """Idempotent: the UPDATE only succeeds from created / pending_review, so a payment grants access at most once."""
        cur = self.db.x("UPDATE payments SET status='paid', paid_at=?, provider_payment_id=COALESCE(?,provider_payment_id), method=COALESCE(?,method) WHERE id=? AND status IN ('created','pending_review')",
                        (now_iso(), provider_payment_id, method, pid))
        if cur.rowcount != 1:
            return False
        p = self.db.one('SELECT * FROM payments WHERE id=?', (pid,))
        self.db.x('UPDATE payments SET receipt_no=? WHERE id=?', ('DKR-%s-%06d' % (dt.date.today().year, pid), pid))
        u = self.db.one('SELECT * FROM subscribers WHERE id=?', (p['user_id'],)) if p['user_id'] else None
        if u:
            self._extend(u, p['tier'] if p['tier'] in self.st.tiers else 'platinum', p['plan_days'] or 30)
            u = self.db.one('SELECT * FROM subscribers WHERE id=?', (u['id'],))
            self._receipt_mail(u, self.db.one('SELECT * FROM payments WHERE id=?', (pid,)))
        return True

    def _extend(self, u, tier, days):
        """Same tier: the new period is added after the current end date. Different tier: the days left are converted (carry_days) and the new tier starts today."""
        today = dt.date.today()
        base = self.carry_days(u, tier)
        self.db.x('UPDATE subscribers SET plan_until=?, plan_tier=? WHERE id=?', ((today + dt.timedelta(days=base + days)).isoformat(), tier, u['id']))

    def receipt(self, u, pid):
        p = self._own(u, pid)
        if p['status'] != 'paid' or not p['amount_paise']:
            raise ApiError('No receipt for this payment.', 404)
        total = p['amount_paise'] / 100
        g = self.st.gst_percent
        base = round(total / (1 + g / 100), 2) if g else total
        return {'receipt_no': p['receipt_no'], 'date': (p['paid_at'] or '')[:10], 'billed_to': p['billed_name'], 'email': u['email'], 'item': self._plan_label(p),
                'plan_days': p['plan_days'], 'amount': round(total, 2), 'taxable': base, 'gst_percent': g, 'gst': round(total - base, 2), 'method': p['method'],
                'reference': p['provider_payment_id'], 'seller': self.st.business_name, 'gstin': self.st.gstin, 'valid_until': u['plan_until']}

    def _receipt_mail(self, u, p):
        if not p['amount_paise']:
            return
        self.n.send('email', u['email'], 'Hello %s,\n\nThank you. We received Rs %.2f for "%s". Your %s plan is active until %s.\n\nReceipt no: %s\nPayment reference: %s\n\nView / print your receipt: %s/receipt.html?id=%d\n\n'
                    'Questions about a payment? %s\n' % ((u['first_name'] or u['name']).title(), p['amount_paise'] / 100, self._plan_label(p), self.st.tiers[u['plan_tier']]['label'], u['plan_until'], p['receipt_no'], p['provider_payment_id'] or '-',
                                                          self.st.base_url, p['id'], self.st.support_email or 'reply to this email'), subject='%s: payment received - receipt %s' % (self.st.brand, p['receipt_no']), kind='account')

    # -------------------------------------------------------------- history / admin
    def history(self, u):
        out = []
        for p in self.db.q("SELECT * FROM payments WHERE user_id=? AND status IN ('paid','pending_review','rejected') ORDER BY id DESC LIMIT 50", (u['id'],)):
            out.append({'id': p['id'], 'receipt_no': p['receipt_no'], 'amount': p['amount_paise'] / 100, 'status': p['status'], 'method': p['method'], 'date': (p['paid_at'] or p['created_at'] or '')[:10], 'days': p['plan_days'], 'item': self._plan_label(p), 'note': p['note'] if p['status'] == 'rejected' else None})
        return out

    def admin_list(self):
        rows = self.db.q("SELECT p.*, s.email semail, s.phone sphone FROM payments p LEFT JOIN subscribers s ON s.id=p.user_id "
                         "WHERE p.status IN ('pending_review','paid','rejected') ORDER BY (p.status='pending_review') DESC, p.id DESC LIMIT 100")
        return [{'id': r['id'], 'name': r['billed_name'], 'email': r['semail'], 'phone': r['sphone'], 'provider': r['provider'], 'method': r['method'], 'amount': r['amount_paise'] / 100, 'status': r['status'], 'item': (r['tier'] or 'platinum') + ('/' + r['period'] if r['period'] else ''),
                 'utr': r['utr'], 'ref': r['provider_payment_id'], 'created_at': r['created_at'], 'paid_at': r['paid_at'], 'note': r['note']} for r in rows]

    def admin_review(self, pid, approve, note=''):
        p = self.db.one('SELECT * FROM payments WHERE id=?', (pid,))
        if not p or p['status'] != 'pending_review':
            raise ApiError('This payment is not waiting for review.', 404)
        if approve:
            self.mark_paid(pid, p['utr'], 'upi')
            return {'status': 'paid'}
        note = re.sub(r'\s+', ' ', str(note or ''))[:200] or 'Could not match this reference to a bank credit.'
        self.db.x("UPDATE payments SET status='rejected', note=?, reviewed_at=? WHERE id=?", (note, now_iso(), pid))
        u = self.db.one('SELECT * FROM subscribers WHERE id=?', (p['user_id'],)) if p['user_id'] else None
        if u:
            self.n.send('email', u['email'], 'Hello %s,\n\nWe could not confirm your UPI payment (reference %s): %s\n\nIf you did pay, reply with a screenshot of the payment and we will sort it out.\n' % ((u['first_name'] or u['name']).title(), p['utr'], note),
                        subject='%s: we could not confirm your payment' % self.st.brand, kind='account')
        return {'status': 'rejected'}

    def admin_grant(self, email, tier, days, note=''):
        """Give someone a membership without a payment (support gesture, refund-with-access, partner). Recorded as a zero-amount payment."""
        u = self.db.one('SELECT * FROM subscribers WHERE email=? AND password_hash IS NOT NULL', (norm_email(email),))
        if not u:
            raise ApiError('No account with that email.', 404)
        tier = str(tier or '').lower()
        if tier not in self.st.tiers:
            raise ApiError('Choose silver, gold or platinum.')
        days = int(days)
        if not 1 <= days <= 3650:
            raise ApiError('Days must be between 1 and 3650.')
        self.db.x("INSERT INTO payments(user_id,billed_name,provider,method,amount_paise,status,plan_days,tier,note,created_at,paid_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (u['id'], u['name'], 'manual', 'grant', 0, 'paid', days, tier, re.sub(r'\s+', ' ', str(note or ''))[:200], now_iso(), now_iso()))
        self._extend(u, tier, days)
        r = self.db.one('SELECT plan_until, plan_tier FROM subscribers WHERE id=?', (u['id'],))
        return {'plan_until': r['plan_until'], 'tier': r['plan_tier']}
