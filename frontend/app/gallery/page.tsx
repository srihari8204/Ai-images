"use client";

import { useEffect, useState } from "react";
import { api, ApiError, API_BASE } from "@/lib/api";
import type { GalleryItem, Page } from "@/lib/types";

export default function GalleryPage() {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (c?: string | null) => {
    setLoading(true);
    try {
      const q = c ? `?cursor=${encodeURIComponent(c)}` : "";
      const page = await api<Page<GalleryItem>>(`/api/v1/gallery${q}`);
      setItems((prev) => (c ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
      setHasMore(page.has_more);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load gallery");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const update = async (id: string, patch: Partial<GalleryItem>) => {
    const updated = await api<GalleryItem>(`/api/v1/gallery/${id}`, { method: "PATCH", body: patch });
    setItems((xs) => xs.map((x) => (x.id === id ? updated : x)));
  };

  const share = async (id: string) => {
    const item = items.find((x) => x.id === id);
    if (item && item.visibility === "private") await update(id, { visibility: "unlisted" });
    const res = await api<{ share_url: string }>(`/api/v1/gallery/${id}/share`, { method: "POST", body: {} });
    await navigator.clipboard?.writeText(res.share_url).catch(() => {});
    alert(`Share link copied:\n${res.share_url}`);
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this image?")) return;
    await api(`/api/v1/gallery/${id}`, { method: "DELETE" });
    setItems((xs) => xs.filter((x) => x.id !== id));
  };

  return (
    <div>
      <h2>Gallery</h2>
      {error && <div className="error">{error}</div>}
      {!loading && items.length === 0 && <p className="muted">No images yet. Head to the studio.</p>}
      <div className="grid cols-4">
        {items.map((it) => (
          <div className="card" key={it.id} style={{ padding: 10 }}>
            <img className="thumb" src={it.url} alt="" />
            <div className="row" style={{ justifyContent: "space-between", marginTop: 8 }}>
              <span className="badge">{it.visibility}</span>
              <button title="favorite" onClick={() => update(it.id, { is_favorite: !it.is_favorite })}
                style={{ padding: "4px 8px" }}>
                {it.is_favorite ? "★" : "☆"}
              </button>
            </div>
            <div className="row" style={{ marginTop: 8, gap: 6 }}>
              <select value={it.visibility} onChange={(e) => update(it.id, { visibility: e.target.value })}>
                <option value="private">private</option>
                <option value="unlisted">unlisted</option>
                <option value="public">public</option>
              </select>
            </div>
            <div className="row" style={{ marginTop: 8, gap: 6 }}>
              <button onClick={() => share(it.id)} style={{ padding: "6px 10px" }}>Share</button>
              <button onClick={() => remove(it.id)} style={{ padding: "6px 10px" }}>Delete</button>
            </div>
          </div>
        ))}
      </div>
      {hasMore && (
        <button style={{ marginTop: 16 }} disabled={loading} onClick={() => load(cursor)}>
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
