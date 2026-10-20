import { useEffect, useState } from "react";
import { useTranslate } from "@/lib/i18n";

const SHOW_AFTER_PX = 900;

/** A small "back to top" button once the customer has scrolled through the catalog. */
export function BackToTop() {
  const t = useTranslate();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > SHOW_AFTER_PX);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (!visible) return null;
  return (
    <button
      aria-label={t("common.back_to_top")}
      className="back-to-top"
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      type="button"
    >
      <svg aria-hidden="true" className="size-5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" viewBox="0 0 24 24">
        <path d="m6 14 6-6 6 6" />
      </svg>
    </button>
  );
}
