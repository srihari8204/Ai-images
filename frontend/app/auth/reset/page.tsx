"use client";

import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";

function Reset() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/api/v1/auth/password/reset", {
        method: "POST",
        auth: false,
        body: { token, password },
      });
      setDone(true);
      setTimeout(() => router.push("/auth/login"), 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed");
    }
  };

  return (
    <div className="card" style={{ maxWidth: 420, margin: "40px auto" }}>
      <h2>Set a new password</h2>
      {done ? (
        <p className="badge ok">Password updated. Redirecting…</p>
      ) : (
        <form onSubmit={submit}>
          <label>New password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          {error && <div className="error">{error}</div>}
          <button className="primary" style={{ marginTop: 12 }}>Update password</button>
        </form>
      )}
    </div>
  );
}

export default function ResetPage() {
  return (
    <Suspense fallback={<div className="card">Loading…</div>}>
      <Reset />
    </Suspense>
  );
}
