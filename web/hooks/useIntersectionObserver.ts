import { useEffect, useState, useRef, RefObject } from 'react'

interface UseIntersectionObserverOptions {
  threshold?: number | number[]
  root?: Element | null
  rootMargin?: string
  freezeOnceVisible?: boolean
}

export function useIntersectionObserver<T extends Element>(
  options: UseIntersectionObserverOptions = {}
): [RefObject<T>, boolean] {
  const {
    threshold = 0,
    root = null,
    rootMargin = '100px',
    freezeOnceVisible = true
  } = options

  const elementRef = useRef<T>(null)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const element = elementRef.current
    if (!element) return

    // If already visible and frozen, skip
    if (freezeOnceVisible && isVisible) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        const visible = entry.isIntersecting
        if (visible) {
          setIsVisible(true)
          if (freezeOnceVisible) {
            observer.disconnect()
          }
        } else if (!freezeOnceVisible) {
          setIsVisible(false)
        }
      },
      { threshold, root, rootMargin }
    )

    observer.observe(element)

    return () => observer.disconnect()
  }, [threshold, root, rootMargin, freezeOnceVisible, isVisible])

  return [elementRef, isVisible]
}
