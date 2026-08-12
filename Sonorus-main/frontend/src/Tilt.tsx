import React, { useRef, ReactNode } from 'react';

interface TiltProps {
  children: ReactNode;
  className?: string;
  max?: number;
}

/** Real CSS 3D tilt following the cursor -- perspective + rotateX/rotateY,
 * no library. Snaps back smoothly on mouse leave via the transition in CSS. */
export default function Tilt({ children, className, max = 8 }: TiltProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width - 0.5;
    const py = (e.clientY - rect.top) / rect.height - 0.5;
    el.style.transform = `perspective(900px) rotateX(${(-py * max).toFixed(2)}deg) rotateY(${(px * max).toFixed(2)}deg) translateZ(0)`;
  };

  const onMouseLeave = () => {
    const el = ref.current;
    if (!el) return;
    el.style.transform = 'perspective(900px) rotateX(0deg) rotateY(0deg) translateZ(0)';
  };

  return (
    <div
      ref={ref}
      className={`lp-tilt ${className || ''}`}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
    >
      {children}
    </div>
  );
}
