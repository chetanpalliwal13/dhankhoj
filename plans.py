"""Plan catalogue: Free + Silver / Gold / Platinum, each monthly or yearly. All prices come from Settings (never from the browser)."""
PERIODS = {'monthly': 30, 'yearly': 365}
ORDER = ('silver', 'gold', 'platinum')


def free(st):
    return {'key': 'free', 'label': 'Free', 'companies': st.free_companies, 'sms': False, 'whatsapp': False}


def tier(st, key):
    return free(st) if key == 'free' else st.tiers.get(key)


def valid(st, key, period):
    return key in st.tiers and period in PERIODS


def price(st, key, period):
    return st.tiers[key]['monthly' if period == 'monthly' else 'yearly']


def paise(st, key, period):
    return int(round(price(st, key, period) * 100))


def label(st, key, period=None):
    return '%s membership%s' % (st.tiers[key]['label'], (' (%s)' % period) if period else '')


def features(t, st):
    f = ['Unlimited companies shown in full' if t['companies'] is None else 'Up to %d companies shown in full' % t['companies'],
         'Email %s alerts' % ('+ SMS + WhatsApp' if t['whatsapp'] else '+ SMS'),
         'Up to %d demat / folio IDs plus PAN matching' % st.max_dp_ids, 'Deadline reminders before IEPF transfer', 'GST receipts for every payment']
    return f


def public(st):
    out = []
    for k in ORDER:
        t = st.tiers[k]
        full = t['monthly'] * 12
        out.append({'key': k, 'label': t['label'], 'companies': t['companies'], 'sms': t['sms'], 'whatsapp': t['whatsapp'], 'monthly': t['monthly'], 'yearly': t['yearly'],
                    'yearly_per_month': round(t['yearly'] / 12, 2), 'save_percent': max(0, round((1 - t['yearly'] / full) * 100)) if full else 0, 'save_inr': max(0, round(full - t['yearly'])),
                    'features': features(t, st), 'popular': k == 'gold'})
    return out
