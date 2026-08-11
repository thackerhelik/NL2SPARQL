import type { Metadata } from "next";
import "./globals.css";
import { SchemaProvider } from "@/contexts/SchemaContext";
import RootLayoutClient from "./layout-client";

export const metadata: Metadata = {
  title: "NL2SPARQL ",
  description:
    "A tool to convert natural language questions into SPARQL queries using LLMs.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <SchemaProvider>
          <RootLayoutClient>{children}</RootLayoutClient>
        </SchemaProvider>
      </body>
    </html>
  );
}
