import type { Metadata } from "next"
import { Inter, JetBrains_Mono } from "next/font/google"
import "./globals.css"
import "katex/dist/katex.min.css"
import { ThemeProvider } from "@/components/theme-provider"
import { I18nProvider } from "@/lib/i18n/i18n-context"
import { cn } from "@/lib/utils"
import { Toaster } from "@/components/ui/sonner"

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  preload: true,
  fallback: ["system-ui", "-apple-system", "sans-serif"],
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  preload: false, // Code font doesn't need to block rendering
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
})

export const metadata: Metadata = {
  title: {
    default: "Weaver - Deep Research AI Agent",
    template: "%s | Weaver AI",
  },
  description:
    "Enterprise-grade AI Agent platform powered by LangGraph. Deep research, code execution, browser automation, and multi-modal interaction.",
  keywords: [
    "AI Agent",
    "LangGraph",
    "Deep Research",
    "Code Execution",
    "Browser Automation",
    "LLM",
    "FastAPI",
    "Next.js",
  ],
  authors: [{ name: "Weaver Team" }],
  creator: "Weaver",
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL || "https://weaver-demo.vercel.app"
  ),
  openGraph: {
    type: "website",
    locale: "en_US",
    title: "Weaver - Deep Research AI Agent",
    description:
      "Enterprise-grade AI Agent platform with deep research, code execution, and browser automation.",
    siteName: "Weaver AI",
  },
  twitter: {
    card: "summary_large_image",
    title: "Weaver - Deep Research AI Agent",
    description:
      "Enterprise-grade AI Agent platform with deep research, code execution, and browser automation.",
  },
  icons: {
    icon: "/favicon.ico",
  },
  manifest: "/manifest.json",
  robots: {
    index: true,
    follow: true,
  },
}

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0f172a" },
  ],
}


export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={cn(
        "min-h-screen bg-background font-sans antialiased",
        inter.variable,
        jetbrainsMono.variable
      )}>
        <ThemeProvider
          defaultTheme="system"
          storageKey="weaver-theme"
        >
          <I18nProvider>
            {children}
            <Toaster />
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
