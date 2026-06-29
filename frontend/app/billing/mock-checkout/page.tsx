"use client";

// Simulated checkout page for the built-in mock payment provider (no Stripe key).
// In production this route is replaced by the provider's hosted checkout.

import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { API_BASE } from "@/lib/api";

function MockCheckout() {
  const params = useSearchParams();
  const router = useRouter();
  const sessionId = params.get("session_id") || "";
  const plan = params.get("plan") || "";
  const [done, setDone] = useState(false);

  // The mock webhook must be signed; in dev the secret defaults to
  // "mock-webhook-secret". Real fulfillment happens server-side via the webhook.
  const pay = async () => {
    setDone(true);
    setTimeout(() => router.push("/billing?status=success"), 1200);
  };

  return (
    <div className="card" style={{ maxWidth: 460, margin: "40px auto" }}>
      <h2>Mock checkout</h2>
      <p className="muted">Plan: <b>{plan}</b></p>
      <p className="muted" style={{ fontSize: 12 }}>Session: {sessionId}</p>
      <p className="muted" style={{ fontSize: 12 }}>
        This is a development stand-in. Fulfillment is driven by a signed webhook to{" "}
        <code>{API_BASE}/webhooks/payments</code>; send it from your test harness to grant credits.
      </p>
      {done ? <p className="badge ok">Processing… redirecting</p> : (
        <button className="primary" onClick={pay}>Simulate successful payment</button>
      )}
    </div>
  );
}

export default function MockCheckoutPage() {
  return (
    <Suspense fallback={<div className="card">Loading…</div>}>
      <MockCheckout />
    </Suspense>
  );
}
