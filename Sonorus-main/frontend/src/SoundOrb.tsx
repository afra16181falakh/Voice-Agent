import React, { useEffect, useRef } from 'react';

/**
 * Procedural 3D particle sphere rendered on canvas -- no image assets, no
 * WebGL library. Real 3D: points are generated on a sphere, rotated around
 * two axes every frame, perspective-projected to 2D by hand (divide by
 * depth), and drawn back-to-front so the sphere reads as solid rather than
 * a flat scatter of dots. Pulses slightly to suggest sound/voice, which is
 * the actual point of a "Sonorus" hero visual rather than a stock graphic.
 */
export default function SoundOrb() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let dpr = Math.min(window.devicePixelRatio || 1, 2);

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener('resize', resize);

    const POINT_COUNT = 340;
    const RADIUS = 150;
    type Pt = { x: number; y: number; z: number };
    const points: Pt[] = [];
    // Fibonacci sphere distribution -- even coverage, no clustering at poles.
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < POINT_COUNT; i++) {
      const y = 1 - (i / (POINT_COUNT - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const theta = golden * i;
      points.push({ x: Math.cos(theta) * r * RADIUS, y: y * RADIUS, z: Math.sin(theta) * r * RADIUS });
    }

    let rotY = 0;
    let rotX = 0.4;
    let raf = 0;
    let mouseX = 0;
    let mouseY = 0;
    let targetRotYOffset = 0;
    let targetRotXOffset = 0;

    const onMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      mouseX = (e.clientX - rect.left - rect.width / 2) / rect.width;
      mouseY = (e.clientY - rect.top - rect.height / 2) / rect.height;
      targetRotYOffset = mouseX * 0.6;
      targetRotXOffset = -mouseY * 0.4;
    };
    window.addEventListener('mousemove', onMove);

    const start = performance.now();

    const draw = (now: number) => {
      const t = (now - start) / 1000;
      rotY += 0.0032;
      rotX += (0.4 + targetRotXOffset - rotX) * 0.02;
      const rotYTarget = rotY + targetRotYOffset;

      const pulse = 1 + Math.sin(t * 1.6) * 0.045;

      ctx.clearRect(0, 0, width, height);

      const cosY = Math.cos(rotYTarget), sinY = Math.sin(rotYTarget);
      const cosX = Math.cos(rotX), sinX = Math.sin(rotX);

      const projected = points.map(p => {
        // rotate around Y then X
        const x1 = p.x * cosY - p.z * sinY;
        const z1 = p.x * sinY + p.z * cosY;
        const y1 = p.y * cosX - z1 * sinX;
        const z2 = p.y * sinX + z1 * cosX;

        const scaled = { x: x1 * pulse, y: y1 * pulse, z: z2 * pulse };
        const perspective = 480 / (480 + scaled.z);
        return {
          sx: width / 2 + scaled.x * perspective,
          sy: height / 2 + scaled.y * perspective,
          scale: perspective,
          z: scaled.z,
        };
      });

      projected.sort((a, b) => a.z - b.z);

      for (const p of projected) {
        const depth01 = (p.z + RADIUS) / (RADIUS * 2); // 0 (back) .. 1 (front)
        const size = Math.max(0.6, 2.6 * p.scale);
        const alpha = 0.15 + depth01 * 0.65;
        const hue = 222 - depth01 * 30; // deep navy -> brighter blue toward viewer
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, size, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${hue}, 90%, ${55 + depth01 * 20}%, ${alpha})`;
        ctx.fill();
      }

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', onMove);
    };
  }, []);

  return <canvas ref={canvasRef} className="lp-orb-canvas" aria-hidden="true" />;
}
