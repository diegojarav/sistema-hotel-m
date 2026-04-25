import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";


const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Hotel Munich - Staff Portal",
  description: "Hotel Munich Management System - Staff Portal",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  interactiveWidget: "resizes-content",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning on <html> and <body> is the standard Next.js
    // fix for browser extensions that inject attributes into the document
    // (QuillBot adds data-qb-installed; Grammarly adds data-gr-*; Dark Reader
    // adds data-darkreader-*). Without this, every dev session with such an
    // extension installed throws a hydration mismatch warning. Production
    // users without these extensions see no difference. The flag only
    // suppresses warnings for these two specific elements — hydration
    // mismatches inside the tree are still reported.
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}

