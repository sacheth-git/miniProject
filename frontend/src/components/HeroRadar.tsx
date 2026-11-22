import { useEffect, useRef } from "react";

/**
 * Home page backdrop: a radar sweep centred behind the example match card. Blips are jobs found on the
 * sources HireX reads; each lights up and names its role and source as the beam passes, then fades.
 * The pointer lights nearby blips. Static frame under reduced motion.
 */
const ROLES = [
  "Data analyst", "Backend engineer", "ML engineer", "Frontend developer", "DevOps engineer", "Software engineer intern",
  "Product designer", "Embedded engineer", "Data scientist", "Mechanical design engineer", "QA engineer", "Full stack developer",
];
const SOURCES = ["LinkedIn", "Naukri", "Indeed", "Glassdoor", "Greenhouse", "Lever", "Ashby", "Adzuna", "Jooble", "Shine", "Remotive", "Company site"];

interface Blip { r: number; a: number; lit: number; label?: string; size: number }

const TAU = Math.PI * 2;
const FADE = 2.4; // radians behind the beam over which a blip fades out (about 3.4 s)

export function HeroRadar({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let w = 0, h = 0, cx = 0, cy = 0, maxR = 0, raf = 0, running = true, last = 0;
    let sweep = -Math.PI / 2;
    let blips: Blip[] = [];
    const pointer = { x: -9999, y: -9999 };
    const rand = (a: number, b: number) => a + Math.random() * (b - a);

    const seed = () => {
      const n = Math.round(Math.min(70, Math.max(28, (w * h) / 16000)));
      let k = 0;
      blips = Array.from({ length: n }, (_, i) => {
        const labelled = i % 2 === 0;
        const b: Blip = { r: rand(40, maxR * 0.95), a: rand(0, TAU), lit: reduce ? Math.random() : 0, size: rand(1.6, 2.8) };
        if (labelled) {
          b.label = `${ROLES[k % ROLES.length]} · ${SOURCES[(k * 5) % SOURCES.length]}`;
          k += 1;
        }
        return b;
      });
    };

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = Math.max(1, r.width); h = Math.max(1, r.height);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const wide = w >= 1024;
      cx = wide ? w * 0.6 : w * 0.78;
      cy = wide ? h * 0.5 : h * 0.3;
      maxR = Math.hypot(Math.max(cx, w - cx), Math.max(cy, h - cy));
      seed();
      if (reduce) draw();
    };

    function draw() {
      ctx!.clearRect(0, 0, w, h);
      // rings and cross-hair
      ctx!.lineWidth = 1;
      for (let r = 90; r < maxR; r += 90) {
        ctx!.beginPath(); ctx!.arc(cx, cy, r, 0, TAU);
        ctx!.strokeStyle = `rgba(255,255,255,${r % 270 === 0 ? 0.11 : 0.06})`; ctx!.stroke();
      }
      ctx!.strokeStyle = "rgba(255,255,255,0.04)";
      ctx!.beginPath(); ctx!.moveTo(cx - maxR, cy); ctx!.lineTo(cx + maxR, cy); ctx!.moveTo(cx, cy - maxR); ctx!.lineTo(cx, cy + maxR); ctx!.stroke();

      // beam: a fading trail of thin wedges behind the leading edge
      const trail = 1.1, slices = 36;
      for (let i = 0; i < slices; i++) {
        const a1 = sweep - (trail * i) / slices, a0 = sweep - (trail * (i + 1)) / slices;
        ctx!.beginPath(); ctx!.moveTo(cx, cy); ctx!.arc(cx, cy, maxR, a0, a1); ctx!.closePath();
        ctx!.fillStyle = `rgba(240,90,26,${0.2 * (1 - i / slices) ** 2})`; ctx!.fill();
      }
      ctx!.beginPath(); ctx!.moveTo(cx, cy); ctx!.lineTo(cx + Math.cos(sweep) * maxR, cy + Math.sin(sweep) * maxR);
      ctx!.strokeStyle = "rgba(240,90,26,0.55)"; ctx!.lineWidth = 1.5; ctx!.stroke();

      // blips
      ctx!.font = "500 11px Inter, ui-sans-serif, system-ui, sans-serif";
      for (const b of blips) {
        const x = cx + Math.cos(b.a) * b.r, y = cy + Math.sin(b.a) * b.r;
        if (x < -40 || y < -20 || x > w + 40 || y > h + 20) continue;
        // Brightness falls off with how far the blip sits behind the beam's leading edge.
        const behind = (((sweep - b.a) % TAU) + TAU) % TAU;
        let l = behind < FADE ? (1 - behind / FADE) ** 1.4 : 0;
        if (reduce) l = b.lit;
        if (Math.hypot(x - pointer.x, y - pointer.y) < 110) l = Math.max(l, 0.9);
        if (l > 0.35) {
          ctx!.beginPath(); ctx!.arc(x, y, b.size + 4 + (1 - l) * 10, 0, TAU);
          ctx!.strokeStyle = `rgba(240,90,26,${0.4 * l})`; ctx!.lineWidth = 1; ctx!.stroke();
        }
        ctx!.beginPath(); ctx!.arc(x, y, b.size + l * 1.5, 0, TAU);
        ctx!.fillStyle = l > 0.05 ? `rgba(240,90,26,${0.25 + 0.75 * l})` : "rgba(255,255,255,0.18)";
        ctx!.fill();
        if (b.label && l > 0.08) {
          ctx!.fillStyle = `rgba(255,255,255,${0.85 * l})`;
          ctx!.fillText(b.label, x + 9, y + 4);
        }
      }
      // centre
      ctx!.beginPath(); ctx!.arc(cx, cy, 4, 0, TAU); ctx!.fillStyle = "#f05a1a"; ctx!.fill();
    }

    const tick = (t: number) => {
      if (!running) return;
      const dt = last ? Math.min(0.05, (t - last) / 1000) : 0.016;
      last = t;
      sweep = (sweep + dt * 0.7) % TAU;
      draw();
      raf = requestAnimationFrame(tick);
    };

    const onPointer = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      pointer.x = e.clientX - r.left; pointer.y = e.clientY - r.top;
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
