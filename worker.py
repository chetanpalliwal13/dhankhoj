"""Stand-alone worker (alternative to the in-process worker; set WORKER_INTERVAL=0 for the web server).
    python3 worker.py --once     # one cycle (use from cron)
    python3 worker.py            # loop forever
"""
import sys
import time

from server import build


def main():
    st, db, svc = build()
    once = '--once' in sys.argv
    while True:
        print(svc.tick(), file=sys.stderr)
        if once:
            return
        time.sleep(max(st.worker_interval, 30))


if __name__ == '__main__':
    main()
