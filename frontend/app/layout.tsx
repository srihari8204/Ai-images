import "./globals.css";
import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "AI Mirror — Turn one selfie into 280+ AI portraits",
  description:
    "Upload one photo and get yourself reimagined across 280+ AI styles — cinematic, anime, fashion, fantasy and more. No sign-up.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <Nav />
          <main className="container">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
