import { toast } from 'sonner'

type ToastType = 'success' | 'error' | 'info' | 'warning'

interface ToastOptions {
    id?: string
    duration?: number
}

const DEFAULT_DURATION = {
    success: 3000,
    error: 5000,
    info: 4000,
    warning: 4000
}

/**
 * Show a toast notification with automatic deduplication if ID is provided.
 */
export const showToast = (
    message: string,
    type: ToastType = 'info',
    options: ToastOptions = {}
) => {
    const { id, duration } = options
    const toastOptions = {
        id,
        duration: duration || DEFAULT_DURATION[type]
    }

    // Dismiss existing toast with same ID to ensure fresh animation/timer
    // OR rely on sonner's native behavior (updates if exists).
    // Sonner updates content if ID matches. To restart timer/animation, we might need to dismiss first?
    // Usually update is fine.

    switch (type) {
        case 'success':
            toast.success(message, toastOptions)
            break
        case 'error':
            toast.error(message, toastOptions)
            break
        case 'warning':
            toast.warning(message, toastOptions)
            break
        case 'info':
        default:
            toast.message(message, toastOptions)
            break
    }
}

export const showSuccess = (message: string, id?: string) => showToast(message, 'success', { id })
export const showError = (message: string, id?: string) => showToast(message, 'error', { id })
export const showInfo = (message: string, id?: string) => showToast(message, 'info', { id })
