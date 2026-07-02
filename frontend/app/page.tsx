import Link from "next/link";

export default function Home() {
  return (
    <div>
      <div className="hero">
        <span className="pill">✨ 280+ AI styles · powered by your selfie</span>
        <h1>
          Turn one selfie into<br />
          <span className="grad">stunning AI portraits</span>
        </h1>
        <p>
          Upload a single photo and get yourself reimagined across hundreds of
          styles — cinematic, anime, fashion, fantasy and more. Your face,
          beautifully transformed.
        </p>
        <div className="row" style={{ justifyContent: "center", marginTop: 30 }}>
          <Link href="/studio" className="btn primary" style={{ padding: "14px 28px", fontSize: 16 }}>
            Start creating →
          </Link>
          <Link href="/gallery" className="btn" style={{ padding: "14px 24px", fontSize: 16 }}>
            View gallery
          </Link>
        </div>
        <p style={{ marginTop: 18, fontSize: 13 }}>No sign-up. No credit card. Just upload and go.</p>
      </div>

      <div className="grid cols-3" style={{ maxWidth: 980, margin: "10px auto 0", textAlign: "left" }}>
        <div className="card">
          <div style={{ fontSize: 26, marginBottom: 8 }}>🎭</div>
          <h3>280+ styles</h3>
          <p className="muted">Cinematic, anime, fashion, fantasy, professional headshots, and dozens more — browse visually and tap to pick.</p>
        </div>
        <div className="card">
          <div style={{ fontSize: 26, marginBottom: 8 }}>🪞</div>
          <h3>It looks like you</h3>
          <p className="muted">Advanced face technology keeps your real identity across every style. Not a lookalike — you.</p>
        </div>
        <div className="card">
          <div style={{ fontSize: 26, marginBottom: 8 }}>⚡</div>
          <h3>Batches & Surprise Me</h3>
          <p className="muted">Generate 10 at once, or hit Surprise Me for a random mix. Photos stream into your gallery live.</p>
        </div>
      </div>

      <div className="row" style={{ justifyContent: "center", gap: 48, margin: "44px 0 0", flexWrap: "wrap" }}>
        <Stat n="280+" label="Styles" />
        <Stat n="1" label="Photo needed" />
        <Stat n="∞" label="Creations" />
      </div>
    </div>
  );
}

function Stat({ n, label }: { n: string; label: string }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: 34, fontWeight: 800, background: "var(--grad)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
        {n}
      </div>
      <div className="muted" style={{ fontSize: 13 }}>{label}</div>
    </div>
  );
}
