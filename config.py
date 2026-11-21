"""Settings come from environment variables (or a .env file next to this file). No secrets live in code."""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_env(path):
    if not os.path.exists(path):
        return
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        v = v.strip()
        if v[:1] in ('"', "'"):
            q = v[0]
            end = v.find(q, 1)
            v = v[1:end] if end > 0 else v[1:]
        else:
            v = re.split(r'\s+#', ' ' + v, maxsplit=1)[0].strip()  # drop trailing "  # comment"
        os.environ.setdefault(k.strip(), v)


_load_env(os.path.join(HERE, '.env'))


def env(name, default=''):
    return os.environ.get(name, default)


def flag(name, default=False):
    v = os.environ.get(name)
    return default if v is None or not v.strip() else v.strip().lower() in ('1', 'true', 'yes', 'on')


class Settings:
    def __init__(self):
        self.brand = env('BRAND', 'DhanKhoj')
        self.base_url = env('BASE_URL', 'http://localhost:8080').rstrip('/')
        self.db_path = env('DB_PATH', os.path.join(HERE, 'data', 'dhankhoj.db'))
        self.host = env('HOST', '127.0.0.1')
        self.port = int(env('PORT', '8080'))
        self.admin_token = env('ADMIN_TOKEN', '')
        self.dev_mode = flag('DEV_MODE', False)  # DEV_MODE=1 returns OTPs in the API response (never in production)
        self.skip_email_verify = flag('SKIP_EMAIL_VERIFY', False) and self.dev_mode  # local demo only: new accounts are treated as email-verified
        self.trust_proxy = flag('TRUST_PROXY', False)
        self.worker_interval = int(env('WORKER_INTERVAL', '120'))  # seconds; 0 disables the in-process worker
        self.crawl_enabled = flag('CRAWL_ENABLED', False)  # worker fetches company pages listed in crawl_targets (needs outbound internet)
        self.otp_ttl = int(env('OTP_TTL', '600'))
        self.salt = env('APP_SALT', 'change-me')
        # accounts / sessions / field encryption
        self.data_key = env('DATA_KEY', '')  # encrypts PAN at rest; long random string. Falls back to APP_SALT (set DATA_KEY in production)
        self.session_days = int(env('SESSION_DAYS', '14'))
        self.verify_ttl = int(env('VERIFY_TTL', str(24 * 3600)))   # email-verification link lifetime (seconds)
        self.reset_ttl = int(env('RESET_TTL', '3600'))             # password-reset link lifetime (seconds)
        self.secure_cookies = flag('SECURE_COOKIES', env('BASE_URL', '').startswith('https://'))
        # plans: Free (FREE_COMPANIES companies, email alerts) + three memberships. Prices are INCLUDING any GST.
        # Yearly price = monthly x 12 less YEARLY_DISCOUNT_PERCENT, unless <TIER>_YEARLY_INR is set. <TIER>_COMPANIES=unlimited removes the cap.
        self.free_companies = int(env('FREE_COMPANIES', '5'))
        self.max_dp_ids = 5                                         # demat (DP-Client ID) / folio numbers a member can store
        self.yearly_discount = float(env('YEARLY_DISCOUNT_PERCENT', '20'))
        self.tiers = {}
        for key, label, monthly, companies, wa in (('silver', 'Silver', '49', '25', False), ('gold', 'Gold', '99', '100', True), ('platinum', 'Platinum', '199', 'unlimited', True)):
            up = key.upper()
            m = float(env(up + '_MONTHLY_INR', monthly))
            y = env(up + '_YEARLY_INR', '')
            cos = env(up + '_COMPANIES', companies).lower()
            self.tiers[key] = {'key': key, 'label': label, 'monthly': m, 'yearly': float(y) if y else float(round(m * 12 * (1 - self.yearly_discount / 100))),
                               'companies': None if cos in ('unlimited', '0', '') else int(cos), 'sms': True, 'whatsapp': wa}
        self.gst_percent = float(env('GST_PERCENT', '18'))          # shown on receipts only; set 0 if not GST-registered
        self.business_name = env('BUSINESS_NAME', 'DhanKhoj')
        self.gstin = env('GSTIN', '')
        self.support_email = env('SUPPORT_EMAIL', '')
        # payments: pay_provider = '' (off) | mock (needs DEV_MODE) | razorpay.   UPI direct needs UPI_VPA.
        self.pay_provider = env('PAY_PROVIDER', '').lower()
        self.razorpay_key_id = env('RAZORPAY_KEY_ID')
        self.razorpay_key_secret = env('RAZORPAY_KEY_SECRET')
        self.razorpay_webhook_secret = env('RAZORPAY_WEBHOOK_SECRET')
        self.razorpay_base = env('RAZORPAY_BASE', 'https://api.razorpay.com')
        # Sign in with Google (OAuth 2.0 web-server flow). Create credentials at console.cloud.google.com > APIs & Services > Credentials,
        # type "Web application", and add  <BASE_URL>/auth/google/callback  as an authorised redirect URI.
        self.google_client_id = env('GOOGLE_CLIENT_ID')
        self.google_client_secret = env('GOOGLE_CLIENT_SECRET')
        self.google_auth_url = env('GOOGLE_AUTH_URL', 'https://accounts.google.com/o/oauth2/v2/auth')
        self.google_token_url = env('GOOGLE_TOKEN_URL', 'https://oauth2.googleapis.com/token')
        self.google_userinfo_url = env('GOOGLE_USERINFO_URL', 'https://openidconnect.googleapis.com/v1/userinfo')
        self.upi_vpa = env('UPI_VPA')          # your merchant UPI ID, e.g. dhankhoj@okhdfcbank
        self.upi_payee = env('UPI_PAYEE', env('BRAND', 'DhanKhoj'))
        self.claim_fee_text = env('CLAIM_FEE_TEXT', 'The expert sends you a written fee quote (fixed fee or a percentage of the amount recovered) before any work starts. You can decline at no cost.')
        # providers: console | smtp ; console | twilio | msg91 ; console | twilio | meta
        self.email_provider = env('EMAIL_PROVIDER', 'console')
        self.sms_provider = env('SMS_PROVIDER', 'console')
        self.wa_provider = env('WA_PROVIDER', 'console')
        self.smtp_host = env('SMTP_HOST')
        self.smtp_port = int(env('SMTP_PORT', '587'))
        self.smtp_user = env('SMTP_USER')
        self.smtp_pass = env('SMTP_PASS')
        self.smtp_from = env('SMTP_FROM', 'alerts@example.com')
        self.smtp_mode = env('SMTP_MODE', 'starttls')  # starttls | ssl | none
        self.twilio_sid = env('TWILIO_SID')
        self.twilio_token = env('TWILIO_TOKEN')
        self.twilio_sms_from = env('TWILIO_SMS_FROM')
        self.twilio_messaging_sid = env('TWILIO_MESSAGING_SID')
        self.twilio_wa_from = env('TWILIO_WA_FROM')  # e.g. whatsapp:+14155238886
        self.twilio_base = env('TWILIO_BASE', 'https://api.twilio.com')
        self.msg91_key = env('MSG91_AUTHKEY')
        self.msg91_otp_template = env('MSG91_OTP_TEMPLATE_ID')
        self.msg91_alert_template = env('MSG91_ALERT_TEMPLATE_ID')
        self.msg91_base = env('MSG91_BASE', 'https://control.msg91.com')
        self.meta_token = env('META_WA_TOKEN')
        self.meta_phone_id = env('META_WA_PHONE_ID')
        self.meta_otp_template = env('META_WA_OTP_TEMPLATE')
        self.meta_alert_template = env('META_WA_ALERT_TEMPLATE')
        self.meta_lang = env('META_WA_LANG', 'en')
        self.meta_base = env('META_BASE', 'https://graph.facebook.com/v20.0')
