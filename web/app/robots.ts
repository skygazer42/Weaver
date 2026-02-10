import { MetadataRoute } from 'next'

/**
 * Dynamic robots.txt generation via Next.js Metadata API.
 * Guides search engine crawlers on which paths to index.
 */
export default function robots(): MetadataRoute.Robots {
    const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://weaver-demo.vercel.app'

    return {
        rules: [
            {
                userAgent: '*',
                allow: '/',
                disallow: [
                    '/api/',       // API endpoints should not be indexed
                    '/_next/',     // Next.js internals
                ],
            },
        ],
        sitemap: `${baseUrl}/sitemap.xml`,
    }
}
