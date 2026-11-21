# Turn on "Continue with Google" (10 minutes)

The code is finished and tested. It switches on when the server has a Google Client ID and Secret.

1. Open https://console.cloud.google.com and create a project (for example "DhanKhoj").
2. APIs & Services > OAuth consent screen: choose External, enter the app name, your support email, and add scopes `openid`, `email`, `profile`. Add your own Gmail as a test user while the app is in Testing.
3. APIs & Services > Credentials > Create credentials > OAuth client ID > Web application.
4. Authorised redirect URIs (add every one you will use):
   - `http://localhost:8080/auth/google/callback` (test on your computer)
   - `https://dhankhoj.in/auth/google/callback` (live site, after the server is on a VPS)
5. Copy the Client ID and Client Secret into `.env` next to `server.py`:
   ```
   BASE_URL=http://localhost:8080
   GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=xxxx
   ```
6. Run `python3 server.py`, open http://localhost:8080/signup.html and press "Continue with Google".

If the button is missing, one of the two values is empty or the server was not restarted. If Google shows "redirect_uri_mismatch", the URI in step 4 does not match BASE_URL exactly (http vs https, port, trailing slash).
Before launch, publish the consent screen (Testing mode only allows the test users you listed).
