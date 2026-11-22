import { useEffect, useRef } from "react";

/**
 * Sign-in backdrop: skill tags drift across the panel and link to job nodes (orange) when they come close,
 * the matching idea drawn live. The pointer acts as one more job node. Static frame under reduced motion.
 */
const SKILLS = [
  "Python", "SQL", "React", "Java", "Machine learning", "Excel", "AutoCAD", "Figma", "Node.js", "AWS",
  "Data analysis", "C++", "TypeScript", "Docker", "Power BI", "Embedded C", "Django", "Tableau", "Kotlin",
  "Communication", "Git", "TensorFlow", "Spring Boot", "MATLAB", "Kubernetes", "Product design",
];

interface Node { x: number; y: number; vx: number; vy: number; w: number; label?: string; links: number; glow: number }

export function AuthBackdrop({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let w = 0, h = 0, dpr = 1, raf = 0, running = true;
    let skills: Node[] = [];
    let jobs: Node[] = [];
    const pointer = { x: -9999, y: -9999, active: false };
    const rand = (a: number, b: number) => a + Math.random() * (b - a);

    const seed = () => {
      ctx.font = "500 12px Inter, ui-sans-serif, system-ui, sans-serif";
      const count = Math.max(10, Math.min(SKILLS.length, Math.round((w * h) / 26000)));
      skills = SKILLS.slice(0, count).map((label) => ({
        x: rand(0, w), y: rand(0, h), vx: rand(-0.25, 0.25), vy: rand(-0.2, 0.2),
        w: ctx.measureText(label).width + 20, label, links: 0, glow: 0,
      }));
      const jobCount = Math.max(3, Math.round(count / 4));
      jobs = Array.from({ length: jobCount }, () => ({
        x: rand(w * 0.08, w * 0.92), y: rand(h * 0.08, h * 0.92), vx: rand(-0.12, 0.12), vy: rand(-0.12, 0.12), w: 0, links: 0, glow: 0,
      }));
    };

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      dpr = Math.min(2, window.devicePixelRatio || 1);
      w = Math.max(1, r.width); h = Math.max(1, r.height);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
      if (reduce) draw();
    };

    const move = (n: Node) => {
      n.x += n.vx; n.y += n.vy;
      const pad = n.w / 2 + 10;
      if (n.x < -pad) n.x = w + pad; else if (n.x > w + pad) n.x = -pad;
      if (n.y < -20) n.y = h + 20; else if (n.y > h + 20) n.y = -20;
    };

    function chip(n: Node) {
      const hgt = 26, x = n.x - n.w / 2, y = n.y - hgt / 2, r = 13;
      const lit = Math.min(1, n.glow);
      ctx!.beginPath();
      ctx!.roundRect(x, y, n.w, hgt, r);
      ctx!.fillStyle = `rgba(255,255,255,${0.05 + lit * 0.07})`;
      ctx!.fill();
      ctx!.strokeStyle = lit > 0.05 ? `rgba(240,90,26,${0.25 + lit * 0.55})` : "rgba(255,255,255,0.14)";
      ctx!.lineWidth = 1;
      ctx!.stroke();
      ctx!.fillStyle = `rgba(255,255,255,${0.55 + lit * 0.4})`;
      ctx!.fillText(n.label!, x + 10, n.y + 4);
    }

    function draw() {
      ctx!.clearRect(0, 0, w, h);
      ctx!.font = "500 12px Inter, ui-sans-serif, system-ui, sans-serif";
      const all = pointer.active ? [...jobs, { x: pointer.x, y: pointer.y, vx: 0, vy: 0, w: 0, links: 0, glow: 1 }] : jobs;
      const R = Math.min(190, Math.max(130, w / 5));
      for (const s of skills) s.links = 0;
      // faint web between nearby skills
      ctx!.lineWidth = 1;
      for (let i = 0; i < skills.length; i++) {
        for (let j = i + 1; j < skills.length; j++) {
          const a = skills[i], b = skills[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < 120) {
            ctx!.strokeStyle = `rgba(255,255,255,${0.07 * (1 - d / 120)})`;
            ctx!.beginPath(); ctx!.moveTo(a.x, a.y); ctx!.lineTo(b.x, b.y); ctx!.stroke();
          }
        }
      }
      // skill-to-job matches
      for (const jb of all) {
        jb.links = 0;
        for (const s of skills) {
          const d = Math.hypot(s.x - jb.x, s.y - jb.y);
          if (d < R) {
            const t = 1 - d / R;
            ctx!.strokeStyle = `rgba(240,90,26,${0.15 + t * 0.6})`;
            ctx!.lineWidth = 0.6 + t * 1.2;
            ctx!.beginPath(); ctx!.moveTo(jb.x, jb.y); ctx!.lineTo(s.x, s.y); ctx!.stroke();
            jb.links += 1; s.links += 1;
          }
        }
      }
      for (const s of skills) { s.glow += ((s.links > 0 ? 1 : 0) - s.glow) * 0.08; chip(s); }
      for (const jb of all) {
        jb.glow += (Math.min(1, jb.links / 4) - jb.glow) * 0.06;
        const ring = 9 + jb.glow * 10;
        ctx!.beginPath(); ctx!.arc(jb.x, jb.y, ring, 0, Math.PI * 2);
        ctx!.strokeStyle = `rgba(240,90,26,${0.25 + jb.glow * 0.5})`; ctx!.lineWidth = 1.5; ctx!.stroke();
        ctx!.beginPath(); ctx!.arc(jb.x, jb.y, 4.5, 0, Math.PI * 2);
        ctx!.fillStyle = "#f05a1a"; ctx!.fill();
      }
    }

    // Keep tags readable: nudge overlapping chips apart.
    const separate = () => {
      for (let i = 0; i < skills.length; i++) {
        for (let j = i + 1; j < skills.length; j++) {
          const a = skills[i], b = skills[j];
          const ox = (a.w + b.w) / 2 + 8 - Math.abs(a.x - b.x), oy = 34 - Math.abs(a.y - b.y);
          if (ox > 0 && oy > 0) {
            const sy = a.y < b.y ? -1 : 1;
            a.y += sy * Math.min(oy, 2) * 0.5; b.y -= sy * Math.min(oy, 2) * 0.5;
          }
        }
      }
    };

    const tick = () => {
      if (!running) return;
      separate();
      for (const s of skills) move(s);
      for (const j of jobs) move(j);
      draw();
      raf = requestAnimationFrame(tick);
    };

    const onPointer = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      pointer.active = x >= 0 && y >= 0 && x <= r.width && y <= r.height;
      pointer.x = x; pointer.y = y;
    };
    const onLeave = () => { pointer.active = false; };
    const onVisibility = () => {
      if (reduce) return;
      running = !document.hidden;
      cancelAnimationFrame(raf);
      if (running) raf = requestAnimationFrame(tick);
    };

    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();
    if (!reduce) {
      raf = requestAnimationFrame(tick);
      window.addEventListener("pointermove", onPointer);
      document.addEventListener("pointerleave", onLeave);
      document.addEventListener("visibilitychange", onVisibility);
    }
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("pointermove", onPointer);
      document.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return <canvas ref={ref} aria-hidden className={`pointer-events-none absolute inset-0 h-full w-full ${className}`} />;
}
