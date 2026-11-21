# Payment gateway setup

The code already supports three ways to take payment (see `billing.py`). Pick one in `.env` on the server (the VPS):

1. **Razorpay (cards, UPI, netbanking):** `PAY_PROVIDER=razorpay`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`.
   In the Razorpay dashboard add the webhook `https://YOUR-DOMAIN/api/webhook/razorpay` with events `payment.captured` and `order.paid`, using the same secret.
   Use test keys first (`rzp_test_...`), then switch to live keys after KYC.
2. **Direct UPI with manual approval:** `UPI_VPA=yourname@bank`, `UPI_PAYEE=DhanKhoj`. Customers pay and enter the UTR; you approve it in Admin > Payments.
3. **Mock (testing only):** `DEV_MODE=1` and `PAY_PROVIDER=mock`. No real money.

Admin > Overview > Payment gateway shows which of these are ready. Payments need the Python server (VPS); the static Hostinger site cannot take them.
