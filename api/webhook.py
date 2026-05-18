"""
Mudrost Systems — Stripe Webhook (Vercel Serverless Function)
=============================================================
Deployed automatically when you push to the mudrost-landing repo.
Accessible at: https://mudrostsystems.com/api/webhook

Environment variables (set in Vercel Dashboard > Settings > Environment Variables):
  STRIPE_WEBHOOK_SECRET       — from Stripe Dashboard > Webhooks > signing secret
  MAILERLITE_API_KEY          — your MailerLite API key
  MAILERLITE_BUYERS_GROUP_ID  — 185631523943220974
"""

import os
import json
import stripe
import requests
from http.server import BaseHTTPRequestHandler

MAILERLITE_API_KEY         = os.environ.get("MAILERLITE_API_KEY", "")
MAILERLITE_BUYERS_GROUP_ID = os.environ.get("MAILERLITE_BUYERS_GROUP_ID", "")
STRIPE_WEBHOOK_SECRET      = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

ML_HEADERS = {
    "Authorization": f"Bearer {MAILERLITE_API_KEY}",
    "Content-Type":  "application/json",
    "Accept":        "application/json",
}


def add_buyer_to_mailerlite(email: str, name: str = "") -> bool:
    first_name = name.split()[0] if name else ""
    payload = {
        "email":  email,
        "fields": {"name": first_name} if first_name else {},
        "groups": [MAILERLITE_BUYERS_GROUP_ID],
    }
    r = requests.post(
        "https://connect.mailerlite.com/api/subscribers",
        headers=ML_HEADERS,
        json=payload,
        timeout=10,
    )
    return r.status_code in (200, 201)


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        """Health check."""
        self._respond(200, {"status": "ok"})

    def do_POST(self):
        """Receive Stripe event, verify signature, process purchase."""
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body  = self.rfile.read(content_length)
        sig_header = self.headers.get("Stripe-Signature", "")

        # Verify the request genuinely came from Stripe
        try:
            event = stripe.Webhook.construct_event(
                raw_body, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            self._respond(400, {"error": "Invalid payload"})
            return
        except stripe.error.SignatureVerificationError:
            self._respond(400, {"error": "Invalid signature"})
            return

        # Handle purchase — filter to Mudrost product only ($97 = 9700 cents)
        # This webhook is on the same Stripe account as ERTRS, so we must
        # ignore events from other products.
        if event["type"] == "checkout.session.completed":
            session      = event["data"]["object"]
            amount_total = session.get("amount_total", 0)

            if amount_total != 9700:
                # Not a Mudrost purchase — ignore silently
                self._respond(200, {"received": True, "action": "ignored"})
                return

            customer_details = session.get("customer_details") or {}
            email = customer_details.get("email") or session.get("customer_email", "")
            name  = customer_details.get("name", "")

            if email:
                add_buyer_to_mailerlite(email, name)

        self._respond(200, {"received": True})

    def _respond(self, status: int, body: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        pass  # suppress default access log noise
