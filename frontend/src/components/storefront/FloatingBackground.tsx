import type { CSSProperties } from "react";

type Shape = "clip" | "pencil" | "spark" | "ring" | "ruler" | "eraser" | "pin" | "dots" | "scribble" | "plus";
type Tone = "brand" | "orange" | "sage";

interface FloatingItem {
  shape: Shape;
  tone: Tone;
  left: string;
  top: string;
  size: number;
  rotate: number;
  duration: number;
  delay: number;
}

// Hand-placed so the doodles frame the content instead of sitting under the product grid's
// busiest spots. Negative delays start every item mid-flight on first paint.
const ITEMS: FloatingItem[] = [
  { shape: "clip", tone: "brand", left: "4%", top: "12%", size: 34, rotate: -18, duration: 23, delay: -4 },
  { shape: "spark", tone: "orange", left: "88%", top: "9%", size: 26, rotate: 8, duration: 19, delay: -9 },
  { shape: "pencil", tone: "sage", left: "93%", top: "38%", size: 46, rotate: 32, duration: 27, delay: -2 },
  { shape: "ring", tone: "orange", left: "2%", top: "46%", size: 30, rotate: 0, duration: 21, delay: -13 },
  { shape: "dots", tone: "brand", left: "48%", top: "4%", size: 28, rotate: 12, duration: 25, delay: -6 },
  { shape: "ruler", tone: "sage", left: "7%", top: "78%", size: 48, rotate: -24, duration: 29, delay: -17 },
  { shape: "pin", tone: "orange", left: "84%", top: "70%", size: 28, rotate: 18, duration: 22, delay: -11 },
  { shape: "scribble", tone: "brand", left: "62%", top: "88%", size: 44, rotate: -6, duration: 26, delay: -3 },
  { shape: "plus", tone: "orange", left: "30%", top: "62%", size: 18, rotate: 0, duration: 18, delay: -8 },
  { shape: "eraser", tone: "sage", left: "70%", top: "24%", size: 30, rotate: 22, duration: 24, delay: -15 },
  { shape: "spark", tone: "brand", left: "18%", top: "30%", size: 18, rotate: -10, duration: 20, delay: -5 },
  { shape: "ring", tone: "sage", left: "54%", top: "52%", size: 22, rotate: 0, duration: 28, delay: -19 },
  { shape: "clip", tone: "orange", left: "40%", top: "92%", size: 26, rotate: 40, duration: 24, delay: -12 },
  { shape: "dots", tone: "sage", left: "96%", top: "90%", size: 24, rotate: -20, duration: 21, delay: -7 },
];

function ShapePath({ shape }: { shape: Shape }) {
  switch (shape) {
    case "clip":
      return <path d="M9 7v9a3 3 0 0 0 6 0V5.5a2 2 0 0 0-4 0V15a1 1 0 0 0 2 0V8" />;
    case "pencil":
      return <path d="m4 20 1.2-4.6L16.6 4a2 2 0 0 1 2.8 0l.6.6a2 2 0 0 1 0 2.8L8.6 18.8 4 20Zm10-14 4 4" />;
    case "spark":
      return <path d="M12 3v4m0 10v4M3 12h4m10 0h4M6.3 6.3l2.4 2.4m6.6 6.6 2.4 2.4m0-11.4-2.4 2.4m-6.6 6.6-2.4 2.4" />;
    case "ring":
      return <circle cx="12" cy="12" r="7.5" />;
    case "ruler":
      return <path d="M3 15 15 3l6 6L9 21l-6-6Zm4-1 2 2m1-5 2 2m1-5 2 2" />;
    case "eraser":
      return <path d="M7 19h12M5.5 14.5 13 7a2 2 0 0 1 2.8 0l2.2 2.2a2 2 0 0 1 0 2.8L11.5 18.5H8.5l-3-3a.7.7 0 0 1 0-1Z" />;
    case "pin":
      return <path d="M9 3h6l-1 6 3 3H7l3-3-1-6Zm3 9v9" />;
    case "dots":
      return <path d="M6 6h.01M12 6h.01M18 6h.01M6 12h.01M12 12h.01M18 12h.01M6 18h.01M12 18h.01M18 18h.01" />;
    case "scribble":
      return <path d="M3 14c2-4 4-4 5 0s3 4 5 0 3-4 5 0 2 2 3 1" />;
    case "plus":
      return <path d="M12 5v14M5 12h14" />;
  }
}

/** Slowly drifting stationery doodles behind the storefront. Purely decorative. */
export function FloatingBackground() {
  return (
    <div aria-hidden="true" className="floating-bg">
      {ITEMS.map((item, position) => (
        <span
          className={`floating-item floating-${item.tone}`}
          key={position}
          style={{
            left: item.left,
            top: item.top,
            width: item.size,
            height: item.size,
            animationDuration: `${item.duration}s`,
            animationDelay: `${item.delay}s`,
            "--float-rotate": `${item.rotate}deg`,
          } as CSSProperties}
        >
          <svg fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={item.shape === "dots" ? 3.2 : 1.6} viewBox="0 0 24 24">
            <ShapePath shape={item.shape} />
          </svg>
        </span>
      ))}
    </div>
  );
}
