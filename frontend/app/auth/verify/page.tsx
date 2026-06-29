"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";

function Verify() {
  const params = useSearchParams();
  const token = params.get("token");
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!token) {
      setState("error");
      setMsg("Missing token");
      return;
    }
    api("/api/v1/auth/verify-email", { method: "POST", auth: false, body: { token } })
      .then(() => setState("ok"))
      .catch((e) => {
        setState("error");
        setMsg(e instanceof ApiError ? e.message : "Verification failed");
      });
  }, [token]);

  return (
    <div className="card" style={{ maxWidth: 420, margin: "40px auto" }}>
      <h2>Email verification</h2>
      {state === "working" && <p className="muted">Verifying…</p>}
      {state === "ok" && (
        <>
          <p className="badge ok">Verified</p>
          <p>Your email is confirmed.</p>
          <Link href="/auth/login" className="btn primary">Log in</Link>
        </>
      )}
      {state === "error" && <p className="error">{msg}</p>}
    </div>
  );
}

export default function VerifyPage() {
  return (
    <Suspense fallback={<div className="card">Loading…</div>}>
      <Verify />
    </Suspense>
  );
}
