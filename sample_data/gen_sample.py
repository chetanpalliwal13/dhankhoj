"""Generates FICTIONAL sample unpaid-dividend lists (random names, made-up companies) in two real-world layouts,
then loads them. Run:  python3 sample_data/gen_sample.py   (from the project folder)"""
import csv
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ingest  # noqa: E402
from config import Settings  # noqa: E402
from db import DB  # noqa: E402

FIRST = 'AARAV ANITA ARUN ASHA DEEPAK DIVYA GAURAV GEETA HARISH INDRA JAYA KAVITA KIRAN LALITA MANISH MEENA MOHAMMED NEHA NITIN PADMA PRAKASH PRIYA RAHUL RAJESH RAMESH REKHA SANJAY SARITA SUNIL SURESH SUSHMA UMESH VIJAY VIKRAM VINOD YOGESH ZAINAB FATIMA ABDUL IMRAN SHABANA GURPREET HARPREET JASWANT MANPREET LAKSHMI VENKAT SRINIVAS KRISHNA RADHA SITA GOPAL MUKESH NARESH'.split()
LAST = 'SHARMA VERMA GUPTA SINGH KUMAR PATEL SHAH MEHTA JOSHI DESAI IYER NAIR REDDY RAO KHAN ANSARI QURESHI SIDDIQUI BANERJEE CHATTERJEE MUKHERJEE DAS GHOSH SEN BOSE KAPOOR MALHOTRA AGARWAL JAIN BANSAL MISHRA TIWARI PANDEY YADAV CHAUHAN THAKUR NAIDU PILLAI MENON KURUP GILL SANDHU DHILLON KULKARNI DEShpande'.upper().split()
MID = ['', '', '', 'K', 'R', 'S', 'M', 'KUMAR', 'KUMARI', 'LAL', 'CHAND', 'D', 'P', 'A']
PLACES = [('MUMBAI', '400001'), ('MUMBAI', '400053'), ('PUNE', '411001'), ('DELHI', '110018'), ('NEW DELHI', '110019'), ('JAIPUR', '302001'), ('KOLKATA', '700001'), ('CHENNAI', '600001'),
          ('BENGALURU', '560001'), ('HYDERABAD', '500001'), ('AHMEDABAD', '380001'), ('SURAT', '395001'), ('LUCKNOW', '226001'), ('INDORE', '452001'), ('MOHALI', '160055'), ('KOCHI', '682001'), ('BHOPAL', '462001'), ('NAGPUR', '440001')]
ABROAD = ['DUBAI UAE', 'MUSCAT OMAN', 'SALMIYA KUWAIT', 'SINGAPORE', 'LONDON UK']
STREETS = ['FLAT %d SUNRISE APARTMENTS', 'H NO %d GANDHI NAGAR', 'PLOT %d SECTOR %d', '%d/%d MG ROAD', 'B-%d SHANTI NIKETAN', 'HOUSE %d NEHRU COLONY']


def person(rng):
    n = '%s %s %s' % (rng.choice(FIRST), rng.choice(MID), rng.choice(LAST))
    return ' '.join(n.split())


def address(rng):
    st = rng.choice(STREETS)
    st = st % tuple(rng.randint(1, 240) for _ in range(st.count('%d')))
    if rng.random() < 0.06:
        return st + ' ' + rng.choice(ABROAD), ''
    city, pin = rng.choice(PLACES)
    return st + ' ' + city, pin


def folio(rng):
    k = rng.random()
    if k < 0.45:
        return 'IN30' + ''.join(rng.choice('0123456789') for _ in range(12))
    if k < 0.9:
        return '1201' + ''.join(rng.choice('0123456789') for _ in range(12))
    return str(rng.randint(100000, 999999))


PLANTED = [('ANITA DESAI', '400053'), ('RAJESH K SHARMA', '110018'), ('MOHAMMED IQBAL KHAN', '560001')]


def make_txt(path, n, rng, rate=4.25):
    with open(path, 'w') as f:
        f.write('Unpaid Dividend Details of 1st Interim Dividend for the FY 2026-27\n\n')
        f.write('DIVIDEND TYPE FOLIO NAME ADD1 ADD2 ADD3 ADD4 PINCODE HOLDING NET DIVIDEND\n')
        rows = []
        for i in range(n):
            a, pin = address(rng)
            h = rng.choice([5, 10, 15, 26, 40, 53, 55, 100, 160, 200, 322, 500, 1200])
            rows.append(('%s %s %s' % (folio(rng), person(rng), a), pin, h))
        for nm, pin in PLANTED[:2]:
            a, _ = address(rng)
            rows.insert(rng.randint(0, n), ('%s %s %s' % (folio(rng), nm, a), pin, 160))
        for body, pin, h in rows:
            f.write('INT DIV 2026-27 %s %s %d %.2f\n' % (body, pin, h, h * rate) if pin else 'INT DIV 2026-27 %s %d %.2f\n' % (body, h, h * rate))


def make_csv(path, n, rng, fy, rate):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['FOLIO NO', 'NAME', 'ADDRESS 1', 'ADDRESS 2', 'PINCODE', 'NO OF SHARES', 'AMOUNT (RS)'])
        rows = []
        for i in range(n):
            a, pin = address(rng)
            h = rng.choice([10, 20, 25, 50, 75, 100, 250, 400, 1000])
            rows.append([folio(rng), person(rng), a.split(' ')[0] + ' ' + ' '.join(a.split(' ')[1:3]), ' '.join(a.split(' ')[3:]), pin, h, '%.2f' % (h * rate)])
        for nm, pin in PLANTED[1:]:
            a, _ = address(rng)
            rows.insert(rng.randint(0, n), [folio(rng), nm, a, '', pin, 250, '%.2f' % (250 * rate)])
        w.writerows(rows)


def main():
    rng = random.Random(7)
    st = Settings()
    db = DB(st.db_path)
    jobs = [
        ('sample_power_finance_int_2026-27.txt', 'Sample Power Finance Ltd', lambda p: make_txt(p, 1800, rng), dict(source_url='https://example.com/sample-power-finance-unpaid.pdf', declared_on='2026-11-14')),
        ('demo_steel_final_2025-26.csv', 'Demo Steel Works Ltd', lambda p: make_csv(p, 1200, rng, '2025-26', 6.0), dict(fy='2025-26', dtype='Final', source_url='https://example.com/demo-steel-unclaimed.csv', declared_on='2026-08-20')),
        ('demo_textiles_final_2019-20.csv', 'Demo Textiles Ltd', lambda p: make_csv(p, 600, rng, '2019-20', 2.5), dict(fy='2019-20', dtype='Final', source_url='https://example.com/demo-textiles-unclaimed.csv', declared_on='2019-12-20')),
    ]
    for fname, company, gen, kw in jobs:
        p = os.path.join(HERE, fname)
        gen(p)
        print(company, ingest.ingest_file(db, company, p, **kw))
    print(ingest.stats(db))


if __name__ == '__main__':
    main()
