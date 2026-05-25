import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Walix",
  description: "CRM conversacional con WhatsApp",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="bg-slate-50 text-slate-900 antialiased">{children}</body>
    </html>
  );
}
