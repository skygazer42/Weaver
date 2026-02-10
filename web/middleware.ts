import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Next.js Middleware — Security Headers & CSP
 *
 * Injects production-grade HTTP security headers into every response to
 * mitigate XSS, clickjacking, MIME-sniffing, and other common web attacks.
 *
 * Reference: OWASP Secure Headers Project (2025)
 */

export function middleware(request: NextRequest) {
    const response = NextResponse.next()

    // --- Content Security Policy ---
    // Allow self-hosted resources, inline styles (required by Tailwind / next-themes),
    // and connections to the backend API.
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
    const cspDirectives = [
        "default-src 'self'",
        // Scripts: self + eval needed for Next.js dev mode; nonce preferred in prod
        `script-src 'self' 'unsafe-inline' 'unsafe-eval'`,
        // Styles: self + unsafe-inline for Tailwind CSS / next-themes
        `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`,
        // Images: self + data URIs (base64 charts) + blob + any https
        `img-src 'self' data: blob: https:`,
        // Fonts: Google Fonts CDN
        `font-src 'self' https://fonts.gstatic.com`,
        // API connections
        `connect-src 'self' ${apiUrl} wss: ws: https:`,
        // Frames: deny by default
        "frame-src 'self'",
        // Objects: none
        "object-src 'none'",
        // Base URI: self
        "base-uri 'self'",
        // Form actions
        "form-action 'self'",
        // Upgrade insecure requests in production
        "upgrade-insecure-requests",
    ].join('; ')

    response.headers.set('Content-Security-Policy', cspDirectives)

    // --- Prevent Clickjacking ---
    response.headers.set('X-Frame-Options', 'DENY')

    // --- Prevent MIME-type sniffing ---
    response.headers.set('X-Content-Type-Options', 'nosniff')

    // --- Referrer Policy ---
    response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin')

    // --- Disable legacy XSS Auditor (CSP is the replacement) ---
    response.headers.set('X-XSS-Protection', '0')

    // --- Restrict browser APIs ---
    response.headers.set(
        'Permissions-Policy',
        'camera=(), microphone=(self), geolocation=(), browsing-topics=()'
    )

    // --- Force HTTPS (instruct browsers to only ever use HTTPS) ---
    response.headers.set(
        'Strict-Transport-Security',
        'max-age=63072000; includeSubDomains; preload'
    )

    // --- Hide X-Powered-By (Next.js already does this but belt-and-suspenders) ---
    response.headers.delete('X-Powered-By')

    return response
}

/**
 * Match all routes except static files and Next.js internals.
 */
export const config = {
    matcher: [
        /*
         * Match all request paths except for the ones starting with:
         * - _next/static (static files)
         * - _next/image (image optimization files)
         * - favicon.ico (favicon file)
         * - public folder assets
         */
        '/((?!_next/static|_next/image|favicon\\.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)',
    ],
}
