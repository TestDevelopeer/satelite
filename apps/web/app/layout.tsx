import type { Metadata } from "next";
import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
import { QueryProvider } from "@/components/query-provider";

export const metadata: Metadata = {
  title: "GeoEco Monitor",
  description: "Публичный аналитический дашборд предварительной дистанционной оценки по Sentinel-2.",
  icons: {
    icon: "/favicon.svg"
  }
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
