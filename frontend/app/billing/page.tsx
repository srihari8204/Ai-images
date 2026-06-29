"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Balance, Plan } from "@/lib/types";

interface Invoice {
  id: string;
  amount_cents: number;
  currency: string;
  credits_granted: number;
  kind: string;
  status: string;
  created_at: string;
}

export default function BillingPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [packs, setPacks] = useState<Plan[]>([]);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadAll = () => {
    api<Plan[]>("/api/v1/billing/plans", { auth: false }).then(setPlans).catch(() => {});
    api<Plan[]>("/api/v1/billing/credit-packs", { auth: false }).then(setPacks).catch(() => {});
    api<Balance>("/api/v1/credits/balance").then(setBalance).catch(() => {});
    api<Invoice[]>("/api/v1/billing/invoices").then(setInvoices).catch(() => {});
  };
  useEffect(loadAll, []);

  const checkout = async (slug: string) => {
    setError(null);
    try {
      const res = await api<{ checkout_url: string }>("/api/v1/billing/checkout", {
        method: "POST",
        body: { plan_slug: slug },
      });
      window.location.href = res.checkout_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Checkout failed");
    }
  };

  const downloadInvoice = async (id: string) => {
    const res = await api<{ url: string }>(`/api/v1/billing/invoices/${id}`);
    window.open(res.url, "_blank");
  };

  const money = (c: number, cur: string) => `${(c / 100).toFixed(2)} ${cur}`;

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Billing</h2>
        {balance && <span className="badge ok">Balance: {balance.balance} ({balance.available} available)</span>}
      </div>
      {error && <div className="error">{error}</div>}

      <h3>Subscription plans</h3>
      <div className="grid cols-3">
        {plans.map((p) => (
          <div className="card" key={p.id}>
            <h3>{p.name}</h3>
            <p className="muted">{p.monthly_credits} credits / month</p>
            <p style={{ fontSize: 24, fontWeight: 700 }}>{money(p.price_cents, p.currency)}</p>
            <button className="primary" onClick={() => checkout(p.slug)} disabled={p.price_cents === 0}>
              {p.price_cents === 0 ? "Current" : "Subscribe"}
            </button>
          </div>
        ))}
      </div>

      <h3>Credit packs</h3>
      <div className="grid cols-3">
        {packs.map((p) => (
          <div className="card" key={p.id}>
            <h3>{p.name}</h3>
            <p className="muted">{p.credits} credits</p>
            <p style={{ fontSize: 24, fontWeight: 700 }}>{money(p.price_cents, p.currency)}</p>
            <button className="primary" onClick={() => checkout(p.slug)}>Buy</button>
          </div>
        ))}
      </div>

      <h3>Invoices</h3>
      <div className="card">
        <table>
          <thead><tr><th>Date</th><th>Amount</th><th>Credits</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {invoices.map((iv) => (
              <tr key={iv.id}>
                <td>{new Date(iv.created_at).toLocaleDateString()}</td>
                <td>{money(iv.amount_cents, iv.currency)}</td>
                <td>{iv.credits_granted}</td>
                <td>{iv.status}</td>
                <td><button onClick={() => downloadInvoice(iv.id)} style={{ padding: "4px 8px" }}>Receipt</button></td>
              </tr>
            ))}
            {invoices.length === 0 && <tr><td colSpan={5} className="muted">No invoices yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
