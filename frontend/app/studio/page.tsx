"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, API_BASE, getAccess } from "@/lib/api";
import type { Style, Job, Balance } from "@/lib/types";

const POST_STAGES = [
  { key: "instantid", label: "Face consistency (InstantID)" },
  { key: "controlnet", label: "Structure (ControlNet)" },
  { key: "gfpgan", label: "Face restore (GFPGAN)" },
  { key: "realesrgan", label: "Upscale (RealESRGAN)" },
  { key: "bg_removal", label: "Remove background" },
];

export default function StudioPage() {
  const [styles, setStyles] = useState<Style[]>([]);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [prompt, setPrompt] = useState("");
  const [styleSlug, setStyleSlug] = useState("");
  const [stages, setStages] = useState<string[]>([]);
  const [referenceId, setReferenceId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [photos, setPhotos] = useState(1);
  const [batchMsg, setBatchMsg] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    api<Style[]>("/api/v1/styles", { auth: false })
      .then((s) => {
        setStyles(s);
        if (s.length) setStyleSlug((cur) => cur || s[0].slug); // default a style
      })
      .catch(() => {});
    api<Balance>("/api/v1/credits/balance").then(setBalance).catch(() => {});
    return () => esRef.current?.close();
  }, []);

  const toggleStage = (key: string) =>
    setStages((s) => (s.includes(key) ? s.filter((x) => x !== key) : [...s, key]));

  const upload = async (file: File) => {
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const img = await api<{ id: string }>("/api/v1/uploads", { method: "POST", body: fd });
      setReferenceId(img.id);
      // AI-Mirror flow: uploading a selfie turns on face mode + polish.
      setStages((s) => Array.from(new Set([...s, "instantid", "gfpgan", "realesrgan"])));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    }
  };

  const pollOrStream = (jobId: string) => {
    // Stream progress via SSE (EventSource can't set headers, so token is in query).
    const token = getAccess();
    const es = new EventSource(
      `${API_BASE}/api/v1/jobs/${jobId}/events?access_token=${token ?? ""}`
    );
    esRef.current = es;
    es.onmessage = () => {};
    es.addEventListener("progress", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setJob((j) => (j ? { ...j, status: data.status, progress: data.progress } : j));
      if (["completed", "failed", "cancelled"].includes(data.status)) {
        es.close();
        api<Job>(`/api/v1/jobs/${jobId}`).then(setJob);
      }
    });
    es.onerror = () => {
      // Fall back to polling if SSE drops.
      es.close();
      const t = setInterval(async () => {
        const j = await api<Job>(`/api/v1/jobs/${jobId}`);
        setJob(j);
        if (["completed", "failed", "cancelled"].includes(j.status)) clearInterval(t);
      }, 2000);
    };
  };

  const submit = async () => {
    setError(null);
    setBatchMsg(null);
    setBusy(true);
    try {
      // Batch mode: generate N photos of the chosen filter (one job each) via
      // the pack endpoint. Results stream into the Gallery.
      if (photos > 1) {
        await api("/api/v1/jobs/pack", {
          method: "POST",
          body: {
            prompt,
            style_slugs: [styleSlug],
            variants_per_style: photos,
            stages: ["generate", ...stages],
            reference_image_ids: referenceId ? [referenceId] : [],
          },
          idempotencyKey: crypto.randomUUID(),
        });
        setBatchMsg(`${photos} photos are generating — they'll appear in your Gallery shortly.`);
        api<Balance>("/api/v1/credits/balance").then(setBalance).catch(() => {});
        return;
      }
      const body = {
        prompt,
        style_slug: styleSlug || null,
        stages: ["generate", ...stages],
        reference_image_ids: referenceId ? [referenceId] : [],
        params: { width: 1024, height: 1024, steps: 28 },
      };
      const res = await api<{ job_id: string; status: string; cost_credits: number }>(
        "/api/v1/jobs",
        { method: "POST", body, idempotencyKey: crypto.randomUUID() }
      );
      setJob({
        id: res.job_id,
        status: res.status,
        progress: 0,
        cost_credits: res.cost_credits,
        prompt,
        stages: body.stages,
        error_message: null,
        created_at: new Date().toISOString(),
        result_image_ids: [],
      });
      pollOrStream(res.job_id);
      api<Balance>("/api/v1/credits/balance").then(setBalance).catch(() => {});
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Submission failed");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!job) return;
    await api(`/api/v1/jobs/${job.id}/cancel`, { method: "POST" });
    setJob({ ...job, status: "cancelled" });
  };

  return (
    <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", alignItems: "start" }}>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2>Studio</h2>
          {balance && <span className="badge">Available: {balance.available} credits</span>}
        </div>

        <label>Details (optional)</label>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
          placeholder="Optional — leave empty to use the style as-is" />

        <label>Style</label>
        <select value={styleSlug} onChange={(e) => setStyleSlug(e.target.value)}>
          <option value="">None</option>
          {styles.map((s) => (
            <option key={s.id} value={s.slug}>
              {s.name} {s.plan_gate ? `(${s.plan_gate})` : ""} ×{s.cost_multiplier}
            </option>
          ))}
        </select>

        <label>Photos</label>
        <select value={photos} onChange={(e) => setPhotos(Number(e.target.value))}>
          {[1, 2, 4, 6, 8, 10].map((n) => (
            <option key={n} value={n}>{n} photo{n > 1 ? "s" : ""}</option>
          ))}
        </select>

        <label>Post-processing</label>
        <div className="grid cols-3">
          {POST_STAGES.map((st) => (
            <label key={st.key} className="row" style={{ fontSize: 13 }}>
              <input type="checkbox" style={{ width: "auto" }}
                checked={stages.includes(st.key)} onChange={() => toggleStage(st.key)} />
              {st.label}
            </label>
          ))}
        </div>

        <label>Reference image (for face/structure)</label>
        <input type="file" accept="image/*"
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        {referenceId && <p className="badge ok">Reference uploaded</p>}
        {stages.includes("instantid") && (
          <p className="muted" style={{ fontSize: 12 }}>
            Face consistency requires recorded biometric consent — see{" "}
            <a href="/settings">settings</a>.
          </p>
        )}

        {error && <div className="error">{error}</div>}
        <button className="primary" style={{ marginTop: 16 }} disabled={busy || !styleSlug}
          onClick={submit}>
          {busy ? "Submitting…" : "Generate"}
        </button>
      </div>

      <div className="card">
        <h3>Result</h3>
        {batchMsg && (
          <div className="badge ok" style={{ display: "block", marginBottom: 12 }}>
            {batchMsg} <a href="/gallery">Open gallery →</a>
          </div>
        )}
        {!job && !batchMsg && (
          <p className="muted">Upload your photo, pick a style, and hit Generate.</p>
        )}
        {job && (
          <>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span className={`badge ${job.status === "completed" ? "ok" : job.status === "failed" ? "err" : ""}`}>
                {job.status}
              </span>
              <span className="muted">{job.cost_credits} credits</span>
            </div>
            <div className="progress" style={{ marginTop: 10 }}>
              <div style={{ width: `${job.progress}%` }} />
            </div>
            {job.error_message && <div className="error">{job.error_message}</div>}
            {["queued", "running"].includes(job.status) && (
              <button style={{ marginTop: 12 }} onClick={cancel}>Cancel</button>
            )}
            {job.result_image_ids?.length > 0 && (
              <div className="grid cols-3" style={{ marginTop: 16 }}>
                {job.result_image_ids.map((id) => (
                  <ResultImage key={id} id={id} />
                ))}
              </div>
            )}
            {job.status === "completed" && (
              <p style={{ marginTop: 12 }}><a href="/gallery">View in gallery →</a></p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function ResultImage({ id }: { id: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    api<{ url: string }>(`/api/v1/gallery/${id}`).then((d) => setUrl(d.url)).catch(() => {});
  }, [id]);
  return url ? <img className="thumb" src={url} alt="result" /> : <div className="thumb" />;
}
