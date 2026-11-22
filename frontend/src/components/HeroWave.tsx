import { useEffect, useRef } from "react";

/**
 * Home page backdrop: a field of dots seen in perspective, rolling like a landscape. Crests catch the
 * orange accent; the pointer sends ripples through the field. Static frame under reduced motion.
 */
export function HeroWave({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let w = 0, h = 0, raf = 0, running = true, last = 0, time = 0;
    const pointer = { x: -9999, y: -9999, energy: 0 };

    const ROWS = 42;
    const Z_NEAR = 1, Z_FAR = 9, CAM_H = 1.6, AMP = 0.42;

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = Math.max(1, r.width); h = Math.max(1, r.height);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw(); // resizing clears the canvas; repaint at once so there is never a blank frame
    };

    function draw() {
      ctx!.clearRect(0, 0, w, h);
      const horizon = h * 0.3;
      const focal = h * 0.62;
      const t = time;
      // far rows first so near dots paint over
      for (let j = ROWS - 1; j >= 0; j--) {
        // geometric depth steps give evenly spaced rows on screen
        const z = Z_NEAR * (Z_FAR / Z_NEAR) ** (j / (ROWS - 1));
        const s = focal / z;
        const depth = 1 - j / (ROWS - 1); // 1 near, 0 far
        const step = 9 + depth * 15; // screen spacing between dots in this row
        for (let off = -w / 2 - step; off <= w / 2 + step; off += step) {
          const x = off / s;
          // layered swells
          let y = AMP * Math.sin(x * 0.35 + t * 0.9) * Math.cos(z * 0.7 - t * 0.6)
            + AMP * 0.45 * Math.sin(x * 0.8 - z * 1.3 + t * 1.4);
          let sx = w / 2 + x * s;
          let sy = horizon + (CAM_H - y) * s * 0.55;
          // pointer ripple in screen space
          if (pointer.energy > 0.01) {
            const d = Math.hypot(sx - pointer.x, sy - pointer.y);
            if (d < 320) {
              const k = Math.exp(-d / 120) * pointer.energy;
              const lift = Math.sin(d * 0.06 - t * 6) * 14 * k;
              sy -= lift;
              y += (lift / 14) * AMP * 1.2;
            }
          }
          if (sx < -10 || sx > w + 10 || sy < -10 || sy > h + 10) continue;
          const crest = Math.min(1, Math.max(0, (y + AMP * 1.45) / (AMP * 2.9)));
          const alpha = (0.12 + depth * 0.55) * (0.45 + crest * 0.75);
          const r = 0.6 + depth * 1.7 + crest * 0.6;
          ctx!.beginPath();
          ctx!.arc(sx, sy, r, 0, Math.PI * 2);
          ctx!.fillStyle = crest > 0.68
            ? `rgba(240,90,26,${Math.min(1, alpha * 1.25)})`
            : `rgba(214,220,235,${alpha * 0.7})`;
          ctx!.fill();
        }
      }
    }

    const tick = (now: number) => {
      if (!running) return;
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 0.016;
      last = now;
      time += dt;
      pointer.energy *= 1 - dt * 0.9;
      draw();
      raf = requestAnimationFrame(tick);
    };

    const onPointer = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      if (x < 0 || y < 0 || x > r.width || y > r.height) return;
      pointer.x = x; pointer.y = y; pointer.energy = 1;
    };
    const onVisibility = () => {
      if (reduce) return;
      running = !document.hidden;
      cancelAnimationFrame(raf);
      last = 0;
      if (running) raf = requestAnimationFrame(tick);
    };

    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();
    if (!reduce) {
      raf = requestAnimationFrame(tick);
      window.addEventListener("pointermove", onPointer);
      document.addEventListener("visibilitychange", onVisibility);
    }
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("pointermove", onPointer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return <canvas ref={ref} aria-hidden className={`pointer-events-none absolute inset-0 h-full w-full ${className}`} />;
}
