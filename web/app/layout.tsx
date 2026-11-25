import type { Metadata } from "next"
import { Inter, JetBrains_Mono, Noto_Sans_SC } from "next/font/google"
import "./globals.css"
import "katex/dist/katex.min.css"
import { ThemeProvider } from "@/components/theme-provider"
import { I18nProvider } from "@/lib/i18n/i18n-context"
import { cn } from "@/lib/utils"
import { Toaster } from "@/components/ui/sonner"

const inter = Inter({ 
  subsets: ["latin"],
  variable: "--font-sans",
})

const notoSansSC = Noto_Sans_SC({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  preload: false,
  variable: "--font-sans-sc",
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
})

export const metadata: Metadata = {
  title: "Weaver — AI Research Workbench",
  description: "An AI agent and deep research workbench for evidence, analysis, and execution.",
  icons: {
    icon: '/favicon.ico', 
  }
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={cn(
        "min-h-screen bg-background font-sans",
        inter.variable,
        notoSansSC.variable,
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
