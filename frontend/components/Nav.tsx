"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

// Login-free product: no auth or billing links. A guest session is opened
// automatically (see lib/auth), so visitors can generate immediately.
export default function Nav() {
  const { user } = useAuth();
  return (
    <nav className="nav">
      <Link href="/" className="brand">AI Mirror</Link>
      <Link href="/studio">Studio</Link>
      <Link href="/gallery">Gallery</Link>
      {user?.roles?.some((r) => r === "admin" || r === "moderator") && (
        <Link href="/admin">Admin</Link>
      )}
      <span className="spacer" />
    </nav>
  );
}
