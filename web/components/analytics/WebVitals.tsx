'use client'

import { useReportWebVitals } from 'next/web-vitals'

export function WebVitals() {
    useReportWebVitals((metric) => {
        // Log detailed metrics in development
        if (process.env.NODE_ENV === 'development') {
            console.log('[Web Vitals]', metric)
        }

        // In production, this would send to an analytics endpoint
        // const body = JSON.stringify(metric)
        // const url = '/api/analytics'
        // if (navigator.sendBeacon) {
        //   navigator.sendBeacon(url, body)
        // } else {
        //   fetch(url, { body, method: 'POST', keepalive: true })
        // }
    })

    return null
}
