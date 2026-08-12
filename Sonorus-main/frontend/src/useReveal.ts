import { useEffect, useRef, useState } from 'react';

/** IntersectionObserver-backed scroll reveal -- returns a ref to attach and
 * whether the element has entered the viewport (stays true once triggered).
 *
 * Two safety nets, both found necessary by actually testing the page
 * end-to-end (not assumed): a generous rootMargin fires the reveal well
 * before the element is literally on screen, and a hard fallback timeout
 * forces visible=true regardless of the observer. Without these, a
 * full-page capture/fast-scroll/any observer edge case left entire
 * below-the-fold sections permanently at opacity:0 -- confirmed directly
 * with a real headless-browser screenshot showing large blank gaps where
 * whole sections should have been. A cosmetic fade-in must never be able
 * to make real content disappear. */
export default function useReveal<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const fallback = window.setTimeout(() => setVisible(true), 1200);

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            window.clearTimeout(fallback);
            observer.disconnect();
          }
        }
      },
      { threshold: 0.05, rootMargin: '300px 0px 300px 0px' }
    );
    observer.observe(el);

    return () => {
      observer.disconnect();
      window.clearTimeout(fallback);
    };
  }, []);

  return { ref, visible };
}
