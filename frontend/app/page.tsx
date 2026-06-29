import Link from "next/link";

export default function Home() {
  return (
    <div className="hero">
      <h1>Create stunning images with AI</h1>
      <p className="muted">
        FLUX.1 generation with face consistency, style presets, upscaling, and more —
        all through a fast, API-first platform.
      </p>
      <div className="row" style={{ justifyContent: "center", marginTop: 24 }}>
        <Link href="/auth/register" className="btn primary">Get started</Link>
        <Link href="/studio" className="btn">Open studio</Link>
      </div>
      <div className="grid cols-3" style={{ marginTop: 48, textAlign: "left" }}>
        <div className="card">
          <h3>Style presets</h3>
          <p className="muted">Photorealistic, cinematic, anime, and premium styles.</p>
        </div>
        <div className="card">
          <h3>Face consistency</h3>
          <p className="muted">InstantID keeps your identity across generations (with consent).</p>
        </div>
        <div className="card">
          <h3>Credits & plans</h3>
          <p className="muted">Pay-as-you-go credit packs or monthly subscriptions.</p>
        </div>
      </div>
    </div>
  );
}
