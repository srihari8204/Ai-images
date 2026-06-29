"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function ForgotPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    await api("/api/v1/auth/password/forgot", {
      method: "POST",
      auth: false,
      body: { email },
    });
    setDone(true);
  };

  return (
    <div className="card" style={{ maxWidth: 420, margin: "40px auto" }}>
      <h2>Reset password</h2>
      {done ? (
        <p className="muted">If the account exists, a reset link has been sent.</p>
      ) : (
        <form onSubmit={submit}>
          <label>Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <button className="primary" style={{ marginTop: 12 }}>Send reset link</button>
        </form>
      )}
    </div>
  );
}
