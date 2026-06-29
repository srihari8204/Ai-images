"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Tab = "users" | "jobs" | "reports" | "moderation" | "flags";

export default function AdminPage() {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState<Tab>("users");

  if (loading) return <p className="muted">Loading…</p>;
  if (!user || !user.roles.some((r) => r === "admin" || r === "moderator")) {
    return <div className="card"><h2>Forbidden</h2><p className="muted">Admin access required.</p></div>;
  }

  return (
    <div>
      <h2>Admin</h2>
      <div className="row" style={{ marginBottom: 16 }}>
        {(["users", "jobs", "reports", "moderation", "flags"] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? "primary" : ""} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      {tab === "users" && <Users />}
      {tab === "jobs" && <Jobs />}
      {tab === "reports" && <Reports />}
      {tab === "moderation" && <Moderation />}
      {tab === "flags" && <Flags />}
    </div>
  );
}

function Users() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const load = () => api<any[]>(`/api/v1/admin/users?q=${encodeURIComponent(q)}`).then(setRows).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  const suspend = async (id: string, suspend: boolean) => {
    await api(`/api/v1/admin/users/${id}/suspend`, { method: "POST", body: { suspend } });
    load();
  };
  const grant = async (id: string) => {
    const amount = Number(prompt("Credits to grant?") || "0");
    if (amount > 0) { await api(`/api/v1/admin/users/${id}/credits`, { method: "POST", body: { amount, reason: "admin" } }); alert("Granted"); }
  };
  return (
    <div className="card">
      <div className="row"><input placeholder="search email" value={q} onChange={(e) => setQ(e.target.value)} />
        <button onClick={load}>Search</button></div>
      <table><thead><tr><th>Email</th><th>Status</th><th>Roles</th><th></th></tr></thead>
        <tbody>{rows.map((u) => (
          <tr key={u.id}><td>{u.email}</td><td>{u.status}</td><td>{u.roles.join(", ")}</td>
            <td className="row">
              <button onClick={() => suspend(u.id, u.status !== "suspended")} style={{ padding: "4px 8px" }}>
                {u.status === "suspended" ? "Reinstate" : "Suspend"}</button>
              <button onClick={() => grant(u.id)} style={{ padding: "4px 8px" }}>+Credits</button>
            </td></tr>))}</tbody></table>
    </div>
  );
}

function Jobs() {
  const [rows, setRows] = useState<any[]>([]);
  const load = () => api<any[]>("/api/v1/admin/jobs").then(setRows).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  const requeue = async (id: string) => { await api(`/api/v1/admin/jobs/${id}/requeue`, { method: "POST" }); alert("Requeued"); load(); };
  const cancel = async (id: string) => { await api(`/api/v1/admin/jobs/${id}/cancel`, { method: "POST" }); load(); };
  return (
    <div className="card">
      <table><thead><tr><th>ID</th><th>Status</th><th>Cost</th><th>Error</th><th></th></tr></thead>
        <tbody>{rows.map((j) => (
          <tr key={j.id}><td>{j.id.slice(0, 8)}</td><td>{j.status}</td><td>{j.cost_credits}</td>
            <td>{j.error_code || ""}</td>
            <td className="row">
              <button onClick={() => requeue(j.id)} style={{ padding: "4px 8px" }}>Requeue</button>
              <button onClick={() => cancel(j.id)} style={{ padding: "4px 8px" }}>Cancel</button>
            </td></tr>))}</tbody></table>
    </div>
  );
}

function Reports() {
  const [rev, setRev] = useState<any>(null);
  const [usage, setUsage] = useState<any>(null);
  useEffect(() => {
    api("/api/v1/admin/reports/revenue").then(setRev).catch(() => {});
    api("/api/v1/admin/reports/usage").then(setUsage).catch(() => {});
  }, []);
  return (
    <div className="grid cols-3">
      <div className="card"><h3>Revenue (30d)</h3>
        {rev && <ul>
          <li>Gross: {(rev.gross_revenue_cents / 100).toFixed(2)}</li>
          <li>Refunds: {(rev.refunds_cents / 100).toFixed(2)}</li>
          <li>Net: {(rev.net_revenue_cents / 100).toFixed(2)}</li>
          <li>Credits used: {rev.credits_consumed}</li></ul>}</div>
      <div className="card"><h3>Usage (30d)</h3>
        {usage && <ul>
          <li>Jobs: {usage.total_jobs}</li>
          <li>Completed: {usage.completed_jobs}</li>
          <li>Active users: {usage.active_users}</li></ul>}</div>
    </div>
  );
}

function Moderation() {
  const [rows, setRows] = useState<any[]>([]);
  const load = () => api<any[]>("/api/v1/admin/moderation?decision=pending").then(setRows).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  const decide = async (id: string, decision: string) => {
    await api(`/api/v1/admin/moderation/${id}/decision`, { method: "POST", body: { decision } });
    load();
  };
  return (
    <div className="card">
      <table><thead><tr><th>Subject</th><th>Classifier</th><th>Score</th><th></th></tr></thead>
        <tbody>{rows.map((m) => (
          <tr key={m.id}><td>{m.subject_type}</td><td>{m.classifier}</td><td>{m.score}</td>
            <td className="row">
              <button onClick={() => decide(m.id, "approved")} style={{ padding: "4px 8px" }}>Approve</button>
              <button onClick={() => decide(m.id, "rejected")} style={{ padding: "4px 8px" }}>Reject</button>
            </td></tr>))}
          {rows.length === 0 && <tr><td colSpan={4} className="muted">Queue empty.</td></tr>}</tbody></table>
    </div>
  );
}

function Flags() {
  const [rows, setRows] = useState<any[]>([]);
  const load = () => api<any[]>("/api/v1/admin/flags").then(setRows).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  const toggle = async (key: string, value: any) => {
    await api(`/api/v1/admin/flags/${key}`, { method: "PUT", body: { value } });
    load();
  };
  return (
    <div className="card">
      <table><thead><tr><th>Key</th><th>Value</th><th></th></tr></thead>
        <tbody>{rows.map((f) => (
          <tr key={f.key}><td>{f.key}</td><td><code>{JSON.stringify(f.value)}</code></td>
            <td><button style={{ padding: "4px 8px" }}
              onClick={() => toggle(f.key, { ...f.value, enabled: !f.value.enabled })}>Toggle</button></td>
          </tr>))}</tbody></table>
    </div>
  );
}
