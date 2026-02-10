import { useEffect, useRef, RefObject } from 'react'

const FOCUSABLE_SELECTOR = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
].join(', ')

/**
 * Reusable focus trap hook for modal dialogs.
 *
 * - Traps Tab and Shift+Tab within the container
 * - Closes on Escape via `onClose` callback
 * - Restores focus to the previously-focused element on unmount
 */
export function useFocusTrap(
    ref: RefObject<HTMLElement | null>,
    isActive: boolean,
    onClose?: () => void,
) {
    // Store the element that was focused before the trap activated
    const previousFocusRef = useRef<HTMLElement | null>(null)

    useEffect(() => {
        if (!isActive || !ref.current) return

        // Save current focus
        previousFocusRef.current = document.activeElement as HTMLElement

        // Focus the first focusable element inside the trap
        const focusableElements = ref.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
        if (focusableElements.length > 0) {
            focusableElements[0]?.focus()
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (!ref.current) return

            // Escape → close
            if (event.key === 'Escape') {
                event.preventDefault()
                onClose?.()
                return
            }

            // Tab trapping
            if (event.key === 'Tab') {
                const focusable = ref.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
                if (focusable.length === 0) return

                const first = focusable[0]
                const last = focusable[focusable.length - 1]

                if (event.shiftKey) {
                    // Shift+Tab: if focus is on first element, wrap to last
                    if (document.activeElement === first) {
                        event.preventDefault()
                        last?.focus()
                    }
                } else {
                    // Tab: if focus is on last element, wrap to first
                    if (document.activeElement === last) {
                        event.preventDefault()
                        first?.focus()
                    }
                }
            }
        }

        document.addEventListener('keydown', handleKeyDown)

        return () => {
            document.removeEventListener('keydown', handleKeyDown)
            // Restore focus to previous element
            previousFocusRef.current?.focus()
        }
    }, [isActive, ref, onClose])
}
