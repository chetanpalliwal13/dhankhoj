"""Delivery of email / SMS / WhatsApp messages through pluggable providers.

Providers (choose with EMAIL_PROVIDER / SMS_PROVIDER / WA_PROVIDER):
  email:     console | smtp
  sms:       console | twilio | msg91
  whatsapp:  console | twilio | meta (WhatsApp Cloud API)
'console' prints the message instead of sending - for development and demos.

India notes: commercial SMS must go through a DLT-registered sender ID and pre-approved templates (TRAI), and business-initiated
WhatsApp messages need pre-approved templates. Set the template ids in .env; variables are passed in a fixed order (see send()).
"""
import base64
import json
import smtplib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage


class Notifier:
    def __init__(self, st):
        self.st = st
        self.sent = []  # in-memory log of console deliveries (tests / demo)

    # --------------------------------------------------------------- public
    def send(self, channel, to, body, subject=None, kind='alert', vars=None):
        """kind: 'otp' | 'alert' | 'reminder'.  vars (ordered) feeds template based providers:
        otp -> {'otp': '123456'};  alert/reminder -> {'name': .., 'count': .., 'amount': .., 'url': ..}.
        Returns (ok, error_text)."""
        try:
            prov = {'email': self.st.email_provider, 'sms': self.st.sms_provider, 'whatsapp': self.st.wa_provider}[channel]
            fn = getattr(self, '_%s_%s' % (channel, prov), None)
            if fn is None:
                return False, 'unknown provider %s for %s' % (prov, channel)
            fn(to, body, subject, kind, vars or {})
            return True, ''
        except Exception as e:  # never raise into the worker
            return False, ('%s: %s' % (type(e).__name__, e))[:300]

    # --------------------------------------------------------------- console
    def _console(self, channel, to, body, subject):
        self.sent.append({'channel': channel, 'to': to, 'subject': subject, 'body': body})
        del self.sent[:-200]
        print('[%s -> %s] %s\n%s\n' % (channel, to, subject or '', body), file=sys.stderr)

    def _email_console(self, to, body, subject, kind, vars):
        self._console('email', to, body, subject)

    def _sms_console(self, to, body, subject, kind, vars):
        self._console('sms', to, body, subject)

    def _whatsapp_console(self, to, body, subject, kind, vars):
        self._console('whatsapp', to, body, subject)

    # --------------------------------------------------------------- email
    def _email_smtp(self, to, body, subject, kind, vars):
        s = self.st
        msg = EmailMessage()
        msg['From'] = s.smtp_from
        msg['To'] = to
        msg['Subject'] = subject or s.brand
        msg.set_content(body)
        msg.add_alternative('<html><body style="font-family:system-ui,Arial,sans-serif;line-height:1.5;color:#1a2333">%s</body></html>' % _html(body), subtype='html')
        if s.smtp_mode == 'ssl':
            srv = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20, context=ssl.create_default_context())
        else:
            srv = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
            if s.smtp_mode == 'starttls':
                srv.starttls(context=ssl.create_default_context())
        try:
            if s.smtp_user:
                srv.login(s.smtp_user, s.smtp_pass)
            srv.send_message(msg)
        finally:
            srv.quit()

    # --------------------------------------------------------------- sms
    def _sms_twilio(self, to, body, subject, kind, vars):
        s = self.st
        data = {'To': to, 'Body': body}
        if s.twilio_messaging_sid:
            data['MessagingServiceSid'] = s.twilio_messaging_sid
        else:
            data['From'] = s.twilio_sms_from
        _http('%s/2010-04-01/Accounts/%s/Messages.json' % (s.twilio_base, s.twilio_sid), form=data, basic=(s.twilio_sid, s.twilio_token))

    def _sms_msg91(self, to, body, subject, kind, vars):
        s = self.st
        tid = s.msg91_otp_template if kind == 'otp' else s.msg91_alert_template
        if not tid:
            raise RuntimeError('MSG91 template id not set for kind=%s' % kind)
        rec = {'mobiles': to.lstrip('+')}
        rec.update(vars)
        _http('%s/api/v5/flow/' % s.msg91_base, js={'template_id': tid, 'short_url': '0', 'recipients': [rec]}, headers={'authkey': s.msg91_key})

    # --------------------------------------------------------------- whatsapp
    def _whatsapp_twilio(self, to, body, subject, kind, vars):
        s = self.st
        _http('%s/2010-04-01/Accounts/%s/Messages.json' % (s.twilio_base, s.twilio_sid), form={'To': 'whatsapp:' + to, 'From': s.twilio_wa_from, 'Body': body}, basic=(s.twilio_sid, s.twilio_token))

    def _whatsapp_meta(self, to, body, subject, kind, vars):
        s = self.st
        tpl = s.meta_otp_template if kind == 'otp' else s.meta_alert_template
        if tpl:
            payload = {'messaging_product': 'whatsapp', 'to': to.lstrip('+'), 'type': 'template',
                       'template': {'name': tpl, 'language': {'code': s.meta_lang},
                                    'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': str(v)} for v in vars.values()]}]}}
        else:  # free text only works inside the 24h customer-service window
            payload = {'messaging_product': 'whatsapp', 'to': to.lstrip('+'), 'type': 'text', 'text': {'body': body}}
        _http('%s/%s/messages' % (s.meta_base, s.meta_phone_id), js=payload, headers={'Authorization': 'Bearer ' + s.meta_token})


def _html(text):
    import html
    import re
    t = html.escape(text).replace('\n', '<br>')
    return re.sub(r'(https?://[^\s<]+)', r'<a href="\1">\1</a>', t)


def _http(url, form=None, js=None, headers=None, basic=None, timeout=15):
    h = dict(headers or {})
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        h['Content-Type'] = 'application/x-www-form-urlencoded'
    elif js is not None:
        data = json.dumps(js).encode()
        h['Content-Type'] = 'application/json'
    if basic:
        h['Authorization'] = 'Basic ' + base64.b64encode(('%s:%s' % basic).encode()).decode()
    req = urllib.request.Request(url, data=data, headers=h, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raise RuntimeError('HTTP %s from provider: %s' % (e.code, e.read().decode('utf-8', 'replace')[:160]))
