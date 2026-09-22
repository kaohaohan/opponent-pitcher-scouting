import type { Metadata } from "next";
import type { ReactNode } from "react";

import { LiveMonitoringProvider } from "@/lib/live-monitoring-provider";
import { QueryProvider } from "@/lib/query-provider";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Baseball Intelligence",
    template: "%s · Baseball Intelligence",
  },
  description: "Pre-game intelligence and player watch operations dashboard.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>
          <LiveMonitoringProvider>{children}</LiveMonitoringProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
