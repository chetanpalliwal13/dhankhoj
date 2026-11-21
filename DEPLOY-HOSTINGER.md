# Hosting DhanKhoj on Hostinger

## Why "index.html not found" happened

DhanKhoj is not a plain static website. The pages live in the `web/` folder, but accounts, alerts, payments and Google sign-in need the Python program (`server.py`) running behind them. If you upload the project into `public_html`, Hostinger looks for `index.html` in that folder, finds none (it is inside `web/`), and shows an error. Moving `web/index.html` up would show the home page but nothing behind it would work.

So the project has to run as a **Python app**. `passenger_wsgi.py` (in the project root) is the startup file Hostinger's Python hosting expects. It serves the home page, every page and the API.

## Which Hostinger plan

* **Web / Cloud hosting with the Python feature** (hPanel > Websites > Advanced > Python, if you see it): follow "Option A".
* **VPS** (any Linux VPS): follow "Option B".
* Plain **PHP/WordPress-only shared hosting without Python**: it cannot run this app. Upgrade the plan or use a VPS.

## Option A: Hostinger Python app

1. In hPanel open **Advanced > Python** for your domain and create a Python app (Python 3.9 or newer).
   * **Application root:** a folder such as `dhankhoj` (not `public_html/web`).
   * **Startup file:** `passenger_wsgi.py`
   * **Entry point:** `application`
2. Upload the project into the application root. Easiest: File Manager > upload `dhankhoj.zip` > Extract, so `passenger_wsgi.py`, `server.py`, `config.py` and the `web/` folder sit together in that root. (`web/` must stay a folder inside it.)
3. Create a file named `.env` in the application root (copy `.env.example`) and set at least:
   ```
   BASE_URL=https://your-domain.com
   APP_SALT=<long random text>
   DATA_KEY=<another long random text>
   ADMIN_TOKEN=<a long secret for the admin page>
   SMTP_HOST=...  SMTP_PORT=587  SMTP_USER=...  SMTP_PASS=...  SMTP_FROM=...   # so verification and reset emails can be sent
   TRUST_PROXY=1
   ```
   Do **not** set `DEV_MODE`. Add `PAY_PROVIDER=razorpay` with the Razorpay keys, and `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` when you are ready (see README).
4. No packages to install: the app uses only Python's standard library.
5. Click **Restart** on the Python app, then open `https://your-domain.com/`. You should see the new home page.
6. **Alerts:** add a cron job (hPanel > Advanced > Cron Jobs), every 15 minutes:
   ```
   cd /home/<user>/<application root> && python3 worker.py --once
   ```
7. **Data:** the database is created in the `data/` folder inside the application root. Back it up regularly, and do not put the project inside a folder that is served as static files.

Payment and Google settings that must match your domain:
* Razorpay webhook URL: `https://your-domain.com/api/webhook/razorpay`
* Google redirect URI: `https://your-domain.com/auth/google/callback`

## Option B: VPS

Copy the project to `/opt/dhankhoj`, create `.env` as above, then use the files in `deploy/`: `dhankhoj.service` (systemd), `nginx.conf` (HTTPS reverse proxy to port 8080) and `crontab.txt` (alert worker). On a VPS the built-in server runs directly: `python3 server.py`.

## If something fails

| Symptom | Likely cause |
|---|---|
| "index.html not found" / 403 / 404 on `/` | The app is not running as a Python app, or `web/` is not inside the application root. |
| 500 error or blank page | Check the app's error log in hPanel. Often a wrong Python version or a missing `.env`. |
| Page works but sign-up says it cannot send email | The `SMTP_*` settings are missing or wrong. |
| Sign-in works but you are logged out on every page | `BASE_URL` is not the `https://` address you are visiting. |
| Old look after an update | Restart the app, then hard-refresh the browser (Ctrl+Shift+R). |
