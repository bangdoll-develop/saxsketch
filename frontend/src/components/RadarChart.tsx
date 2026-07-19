import { useEffect, useRef } from "react";
import type { Tier2 } from "../api";

const KEYS = ["brightness", "power", "resistance", "flexibility", "edge"] as const;

export default function RadarChart({ tier2, compare }: { tier2: Tier2; compare?: Tier2 | null }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current!;
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.clientWidth, H = 200;
    canvas.width = W * dpr; canvas.height = H * dpr;
    const g = canvas.getContext("2d")!;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, W, H);
    const cx = W / 2, cy = H / 2 + 6, R = 74;
    const angle = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / KEYS.length;

    // グリッド
    g.strokeStyle = "#313a47";
    g.fillStyle = "#8b96a6";
    g.font = "11px 'Yu Gothic UI', sans-serif";
    for (const frac of [0.25, 0.5, 0.75, 1]) {
      g.beginPath();
      KEYS.forEach((_, i) => {
        const x = cx + R * frac * Math.cos(angle(i));
        const y = cy + R * frac * Math.sin(angle(i));
        i === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
      });
      g.closePath(); g.stroke();
    }
    KEYS.forEach((k, i) => {
      const x = cx + (R + 16) * Math.cos(angle(i));
      const y = cy + (R + 16) * Math.sin(angle(i));
      g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText(tier2.labels[k] ?? k, x, y);
    });

    const draw = (t: Tier2, stroke: string, fill: string) => {
      g.beginPath();
      KEYS.forEach((k, i) => {
        const r = (R * (t[k] as number)) / 10;
        const x = cx + r * Math.cos(angle(i));
        const y = cy + r * Math.sin(angle(i));
        i === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
      });
      g.closePath();
      g.fillStyle = fill; g.fill();
      g.strokeStyle = stroke; g.lineWidth = 1.8; g.stroke();
    };
    if (compare) draw(compare, "#8b96a6", "rgba(139,150,166,0.12)");
    draw(tier2, "#4da3ff", "rgba(77,163,255,0.22)");
  }, [tier2, compare]);

  return <canvas ref={ref} style={{ width: "100%", height: 200 }} />;
}
