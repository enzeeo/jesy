import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Disaster Relief Caller",
  description: "Caller-facing disaster help request flow",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
