"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

export default function Nav() {
  const { user, logout } = useAuth();
  return (
    <nav className="nav">
      <Link href="/" className="brand">AI Mirror</Link>
      <Link href="/studio">Studio</Link>
      <Link href="/gallery">Gallery</Link>
      <Link href="/billing">Billing</Link>
      {user?.roles?.some((r) => r === "admin" || r === "moderator") && (
        <Link href="/admin">Admin</Link>
      )}
      <span className="spacer" />
      {user ? (
        <>
          <span className="muted">{user.display_name || user.email}</span>
          <button onClick={() => logout()}>Log out</button>
        </>
      ) : (
        <>
          <Link href="/auth/login">Log in</Link>
          <Link href="/auth/register" className="btn primary">Sign up</Link>
        </>
      )}
    </nav>
  );
}
