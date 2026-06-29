"use client";

// OAuth providers redirect here with tokens in the URL fragment
// (#access_token=...&refresh_token=...). We persist them and continue.

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { setTokens } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function Complete() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const frag = new URLSearchParams(window.location.hash.slice(1));
    const access = frag.get("access_token");
    const rfr = frag.get("refresh_token");
    if (access && rfr) {
      setTokens(access, rfr);
      refresh().then(() => router.replace("/studio"));
    } else {
      setError("Missing tokens from provider");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="card" style={{ maxWidth: 420, margin: "40px auto" }}>
      <h2>Finishing sign-in…</h2>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

export default function OAuthCompletePage() {
  return (
    <Suspense fallback={<div className="card">Loading…</div>}>
      <Complete />
    </Suspense>
  );
}
