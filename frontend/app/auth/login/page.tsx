"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { API_BASE, ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      router.push("/studio");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ maxWidth: 420, margin: "40px auto" }}>
      <h2>Log in</h2>
      <form onSubmit={submit}>
        <label>Email</label>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label>Password</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error && <div className="error">{error}</div>}
        <button className="primary" style={{ marginTop: 16 }} disabled={busy}>
          {busy ? "Signing in…" : "Log in"}
        </button>
      </form>
      <div className="row" style={{ marginTop: 16, justifyContent: "space-between" }}>
        <Link href="/auth/forgot">Forgot password?</Link>
        <Link href="/auth/register">Create account</Link>
      </div>
      <div style={{ marginTop: 16 }}>
        <a className="btn" href={`${API_BASE}/api/v1/auth/oauth/google/start`}>Continue with Google</a>{" "}
        <a className="btn" href={`${API_BASE}/api/v1/auth/oauth/apple/start`}>Continue with Apple</a>
      </div>
    </div>
  );
}
