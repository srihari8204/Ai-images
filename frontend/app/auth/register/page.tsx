"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/api/v1/auth/register", {
        method: "POST",
        auth: false,
        body: { email, password, display_name: displayName || null },
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div className="card" style={{ maxWidth: 420, margin: "40px auto" }}>
        <h2>Check your email</h2>
        <p className="muted">
          If the email is available, we sent a verification link. In dev, the link
          is printed to the API logs.
        </p>
        <Link href="/auth/login" className="btn primary">Back to login</Link>
      </div>
    );
  }

  return (
    <div className="card" style={{ maxWidth: 420, margin: "40px auto" }}>
      <h2>Create account</h2>
      <form onSubmit={submit}>
        <label>Display name</label>
        <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        <label>Email</label>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label>Password</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <p className="muted" style={{ fontSize: 12 }}>
          At least 10 characters, mixing letters and numbers.
        </p>
        {error && <div className="error">{error}</div>}
        <button className="primary" style={{ marginTop: 12 }} disabled={busy}>
          {busy ? "Creating…" : "Sign up"}
        </button>
      </form>
      <p style={{ marginTop: 16 }}>
        Already have an account? <Link href="/auth/login">Log in</Link>
      </p>
    </div>
  );
}
