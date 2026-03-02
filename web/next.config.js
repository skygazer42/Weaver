/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Allow e2e / local runs to isolate the Next build output directory so
  // a running `next dev` instance doesn't block Playwright webServer startup.
  distDir: process.env.NEXT_DIST_DIR || '.next',

  // --- Performance ---
  // Hide X-Powered-By header (security best practice)
  poweredByHeader: false,

  // Enable Gzip compression
  compress: true,

  // Standalone output for optimized Docker deployments
  output: 'standalone',

  // Image optimization with modern formats
  images: {
    formats: ['image/avif', 'image/webp'],
    minimumCacheTTL: 60,
    deviceSizes: [640, 750, 828, 1080, 1200, 1920, 2048],
    imageSizes: [16, 32, 48, 64, 96, 128, 256],
  },

  // Dev indicators
  devIndicators: {
    // Next.js DevTools indicator (the draggable "N" in dev).
    // Keep it away from the sidebar's bottom-left controls.
    position: 'bottom-right',
  },

  // Experimental features
  experimental: {
    // Optimize package imports to reduce bundle size
    optimizePackageImports: [
      '@phosphor-icons/react',
      'recharts',
      'framer-motion',
      'react-syntax-highlighter',
      'geist',
    ],
  },

  // --- Security Headers (applied to all routes) ---
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
        ],
      },
      // Cache static assets aggressively
      {
        source: '/(.*)\\.(ico|png|jpg|jpeg|gif|webp|svg|woff|woff2)',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
    ]
  },
}

const withBundleAnalyzer =
  process.env.ANALYZE === 'true'
    ? require('@next/bundle-analyzer')({ enabled: true })
    : (config) => config

module.exports = withBundleAnalyzer(nextConfig)
