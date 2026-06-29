"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Consent { id: string; type: string; version: string; granted_at: string | null; revoked_at: string | null; }

export default function SettingsPage() {
  const { user, loading, refresh } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [consents, setConsents] = useState<Consent[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (user) setDisplayName(user.display_name || "");
    api<Consent[]>("/api/v1/me/consents").then(setConsents).catch(() => {});
  }, [user]);

  if (loading) return <p className="muted">Loading…</p>;
  if (!user) return <div className="card"><h2>Please log in</h2></div>;

  const saveProfile = async () => {
    await api("/api/v1/me", { method: "PATCH", body: { display_name: displayName } });
    await refresh();
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const biometricActive = consents.some(
    (c) => c.type === "biometric" && c.granted_at && !c.revoked_at
  );

  const setConsent = async (granted: boolean) => {
    await api("/api/v1/me/consents", {
      method: "POST",
      body: { type: "biometric", version: "2025-01", granted },
    });
    api<Consent[]>("/api/v1/me/consents").then(setConsents).catch(() => {});
  };

  const requestExport = async () => {
    await api("/api/v1/me/export", { method: "POST" });
    alert("Export requested — you'll be notified when it's ready.");
  };

  const deleteAccount = async () => {
    if (!confirm("Delete your account? This soft-deletes immediately and purges data per retention.")) return;
    await api("/api/v1/me", { method: "DELETE" });
    alert("Account scheduled for deletion.");
  };

  return (
    <div style={{ maxWidth: 600 }}>
      <h2>Settings</h2>
      <div className="card">
        <h3>Profile</h3>
        <label>Display name</label>
        <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        <button className="primary" style={{ marginTop: 12 }} onClick={saveProfile}>Save</button>
        {saved && <span className="badge ok" style={{ marginLeft: 8 }}>Saved</span>}
      </div>

      <div className="card">
        <h3>Biometric consent</h3>
        <p className="muted">
          Required before face-consistency (InstantID) generation processes your facial images.
        </p>
        {biometricActive ? (
          <>
            <p className="badge ok">Consent granted</p>
            <button style={{ marginTop: 8 }} onClick={() => setConsent(false)}>Revoke</button>
          </>
        ) : (
          <button className="primary" onClick={() => setConsent(true)}>Grant consent</button>
        )}
      </div>

      <div className="card">
        <h3>Your data</h3>
        <div className="row">
          <button onClick={requestExport}>Request data export</button>
          <button onClick={deleteAccount} style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
            Delete account
          </button>
        </div>
      </div>
    </div>
  );
}
