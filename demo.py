"""Run DhanKhoj on your own computer with sample data - no email, SMS or payment setup needed.

    python3 demo.py                 # then open http://localhost:8080

What it does: uses a separate database (data/demo.db), loads the lists in sample_data/, skips email verification,
and creates a ready account so you can see matches straight away:

    email: demo@dhankhoj.test    password: Sunrise-Pass-482     (name: Sarita Naidu, PIN 411001)

Any new account whose name and PIN match a name in sample_data/ will also see matches
(for example "Rajesh Ansari" 700001, "Umesh Gupta" 411001, "Aarav Menon" 400001).
Never use this mode on a public server.
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
os.environ.update({'DB_PATH': os.path.join(HERE, 'data', 'demo.db'), 'DEV_MODE': '1', 'SKIP_EMAIL_VERIFY': '1', 'PAY_PROVIDER': 'mock',
                   'EMAIL_PROVIDER': 'console', 'SMS_PROVIDER': 'console', 'WHATSAPP_PROVIDER': 'console', 'BASE_URL': os.environ.get('BASE_URL', 'http://localhost:8080'),
                   'APP_SALT': 'demo-salt', 'DUMMY_DATA_EMAIL': os.environ.get('DUMMY_DATA_EMAIL', 'chetanpalliwal13@gmail.com'), 'ADMIN_TOKEN': os.environ.get('ADMIN_TOKEN', 'demo-admin')})
import ingest  # noqa: E402
import server  # noqa: E402
from auth import Auth  # noqa: E402


def seed(st, db, svc):
    if not db.one('SELECT 1 FROM lists'):
        names = {'demo_steel': 'Demo Steel Ltd', 'demo_textiles': 'Demo Textiles Ltd', 'sample_power': 'Sample Power Finance Ltd'}
        for p in sorted(glob.glob(os.path.join(HERE, 'sample_data', '*'))):
            base = os.path.basename(p)
            co = next((v for k, v in names.items() if base.startswith(k)), None)
            if co and os.path.splitext(p)[1] in ('.csv', '.txt'):
                print('loaded', co, ingest.ingest_file(db, co, p, declared_on='2026-11-14').get('rows'), 'rows')
    au = Auth(svc)
    if not au._by_email('chetanpalliwal13@gmail.com'):
        au.signup({'first_name': 'Chetan', 'last_name': 'Palliwal', 'mobile': '98765 43211', 'email': 'chetanpalliwal13@gmail.com', 'password': 'Blue-Harbor-5821', 'consent': True})
        au.update_profile(au._by_email('chetanpalliwal13@gmail.com'), {'pan': 'ABCPP1234F', 'pincode': '400001'})
        print('sample-data account ready: chetanpalliwal13@gmail.com / Blue-Harbor-5821')
    if not au._by_email('demo@dhankhoj.test'):
        au.signup({'first_name': 'Sarita', 'last_name': 'Naidu', 'mobile': '98765 43210', 'email': 'demo@dhankhoj.test', 'password': 'Sunrise-Pass-482', 'consent': True})
        u = au._by_email('demo@dhankhoj.test')
        au.update_profile(u, {'pan': 'ABCPN1234F', 'pincode': '411001'})
        svc.match_subscriber(u['id'])
        print('demo account ready: demo@dhankhoj.test / Sunrise-Pass-482')


if __name__ == '__main__':
    st, db, svc = server.build()
    seed(st, db, svc)
    server.main()
