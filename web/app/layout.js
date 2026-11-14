import { fetchAll } from "../lib/site-data.mjs";
import { AppProvider } from "./app-context";
import "./globals.css";

// Every page reads live site data (clock, demo roles), so nothing is prerendered at build time.
export const dynamic = "force-dynamic";

export const metadata = {
  title: { default: "GroundIQ", template: "%s · GroundIQ" },
  description: "GroundIQ site context engine: Flags, Evidence review and the digital site model.",
};

export default async function RootLayout({ children }) {
  // Site and crews feed the scenario clock and the demo role switcher on every page.
  const { data } = await fetchAll(process.env.API_BASE_URL, { site: "/site", crews: "/crews" });
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- offline falls back to the system font stacks in globals.css */}
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body>
        <AppProvider site={data?.site || null} crews={data?.crews || []}>{children}</AppProvider>
      </body>
    </html>
  );
}
