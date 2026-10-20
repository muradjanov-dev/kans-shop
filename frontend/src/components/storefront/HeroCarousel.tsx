import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Link } from "react-router-dom";
import { StationeryArt } from "@/components/StationeryArt";
import { useShowcaseProducts } from "@/hooks/queries";
import { useCartActions } from "@/hooks/useCartActions";
import { formatExactPrice } from "@/lib/format";
import { useTranslate } from "@/lib/i18n";
import { hasHigherOldPrice } from "@/lib/productDisplay";
import { useLanguageStore } from "@/store/language";
import type { ShowcaseProduct } from "@/types/api";

export const CAROUSEL_AUTOPLAY_MS = 5000;
const SWIPE_THRESHOLD_PX = 45;
const THUMBNAILS = 5;

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  } catch {
    return false;
  }
}

function productName(product: ShowcaseProduct, language: "uz" | "ru"): string {
  return (language === "ru" ? product.name_ru : product.name_uz) || product.name_uz;
}

/**
 * The storefront's top carousel: a brand slide followed by every active product. It plays
 * on its own, pauses while the customer points at it, focuses it or switches tabs, and can be
 * swiped, stepped with arrows or paused. Reduced-motion users get it without autoplay.
 */
export function HeroCarousel() {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const showcase = useShowcaseProducts();
  const products = showcase.data ?? [];
  const total = products.length + 1;
  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState<"next" | "prev">("next");
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [userPaused, setUserPaused] = useState(false);
  const [pageHidden, setPageHidden] = useState(() => document.visibilityState === "hidden");
  const [reducedMotion] = useState(prefersReducedMotion);
  const pointerStartX = useRef<number | null>(null);
  const swiped = useRef(false);

  const go = useCallback((target: number, nextDirection: "next" | "prev") => {
    setDirection(nextDirection);
    setIndex(((target % total) + total) % total);
  }, [total]);
  const next = useCallback(() => go(index + 1, "next"), [go, index]);
  const previous = useCallback(() => go(index - 1, "prev"), [go, index]);

  useEffect(() => {
    if (index >= total) setIndex(0);
  }, [index, total]);

  useEffect(() => {
    const onVisibility = () => setPageHidden(document.visibilityState === "hidden");
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const playing = total > 1 && !userPaused && !hovered && !focused && !pageHidden && !reducedMotion;

  useEffect(() => {
    if (!playing) return;
    const timer = window.setTimeout(next, CAROUSEL_AUTOPLAY_MS);
    return () => window.clearTimeout(timer);
  }, [next, playing]);

  // Warm the next product image so a slide never appears empty.
  useEffect(() => {
    const upcoming = products[index % Math.max(products.length, 1)];
    if (upcoming?.image_url) {
      const image = new Image();
      image.src = upcoming.image_url;
    }
  }, [index, products]);

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    pointerStartX.current = event.clientX;
    swiped.current = false;
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    if (pointerStartX.current === null) return;
    const distance = event.clientX - pointerStartX.current;
    pointerStartX.current = null;
    if (Math.abs(distance) < SWIPE_THRESHOLD_PX) return;
    swiped.current = true;
    if (distance < 0) next();
    else previous();
  }

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      next();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      previous();
    }
  }

  const product = index === 0 ? null : products[index - 1] ?? null;
  // The next few product slides after the current one (slide s shows products[s - 1]).
  const upcoming = products.length
    ? Array.from({ length: Math.min(THUMBNAILS, products.length) }, (_, offset) => {
        const slide = ((index + offset) % products.length) + 1;
        return { product: products[slide - 1]!, slide };
      })
    : [];

  return (
    <section
      aria-label={t("carousel.label")}
      aria-roledescription={t("carousel.roledescription")}
      className="hero-carousel"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false);
      }}
      onFocus={() => setFocused(true)}
      onKeyDown={onKeyDown}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        className="hero-carousel-stage"
        onClickCapture={(event) => {
          // A swipe must not also open the product it started on.
          if (swiped.current) {
            event.preventDefault();
            event.stopPropagation();
            swiped.current = false;
          }
        }}
        onPointerCancel={() => { pointerStartX.current = null; }}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
      >
        <div
          aria-label={t("carousel.slide", { index: index + 1, total })}
          aria-roledescription={t("carousel.slide_roledescription")}
          className={`hero-slide hero-slide-${direction}`}
          key={index}
          role="group"
        >
          {product ? <ProductSlide language={language} product={product} /> : <BrandSlide />}
        </div>
      </div>

      <div className="hero-carousel-bar">
        <button aria-label={t("carousel.previous")} className="hero-carousel-arrow" disabled={total < 2} onClick={previous} type="button">
          <Chevron direction="left" />
        </button>
        <div aria-hidden="true" className="hero-carousel-progress">
          <span className={playing ? "is-playing" : ""} key={`${index}-${playing}`} />
        </div>
        <span aria-live={playing ? "off" : "polite"} className="hero-carousel-counter">
          {index + 1} / {total}
        </span>
        <button
          aria-label={userPaused ? t("carousel.play") : t("carousel.pause")}
          aria-pressed={userPaused}
          className="hero-carousel-arrow"
          disabled={total < 2}
          onClick={() => setUserPaused((paused) => !paused)}
          type="button"
        >
          {userPaused ? <PlayIcon /> : <PauseIcon />}
        </button>
        <button aria-label={t("carousel.next")} className="hero-carousel-arrow" disabled={total < 2} onClick={next} type="button">
          <Chevron direction="right" />
        </button>
      </div>

      {upcoming.length > 0 && (
        <ul aria-label={t("carousel.upcoming")} className="hero-carousel-thumbs">
          {upcoming.map(({ product: item, slide }) => (
            <li key={`${slide}-${item.id}`}>
              <button
                aria-label={t("carousel.go_to", { name: productName(item, language) })}
                onClick={() => go(slide, slide > index ? "next" : "prev")}
                type="button"
              >
                {item.image_url ? (
                  <img alt="" decoding="async" loading="lazy" src={item.image_url} />
                ) : (
                  <StationeryArt className="size-full" variant={item.name_uz} />
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function BrandSlide() {
  const t = useTranslate();
  return (
    <div className="hero-slide-grid hero-brand-slide">
      <div className="hero-slide-copy">
        <p className="hero-eyebrow">{t("hero.eyebrow")}</p>
        <p className="hero-brand-title">{t("hero.title")}</p>
        <p className="hero-brand-subtitle">{t("hero.subtitle")}</p>
        <div className="hero-slide-actions">
          <a className="primary-button" href="#catalog">
            {t("hero.cta")}
            <span aria-hidden="true">↓</span>
          </a>
        </div>
      </div>
      <div aria-hidden="true" className="hero-slide-visual hero-brand-visual">
        <StationeryArt className="hero-brand-art" />
      </div>
    </div>
  );
}

function ProductSlide({ product, language }: { product: ShowcaseProduct; language: "uz" | "ru" }) {
  const t = useTranslate();
  const { add, pending } = useCartActions();
  const name = productName(product, language);
  const detail = `/product/${product.id}`;
  return (
    <div className="hero-slide-grid">
      <div className="hero-slide-copy">
        <p className="hero-eyebrow">{product.is_featured ? t("product.featured") : t("carousel.from_catalog")}</p>
        <p className="hero-slide-title">
          <Link to={detail}>{name}</Link>
        </p>
        <p className="hero-slide-price">
          <strong>{formatExactPrice(product.price)}</strong> <span>{t("common.som")}</span>
          {hasHigherOldPrice(product.old_price, product.price) && (
            <s className="hero-slide-old-price">{formatExactPrice(product.old_price!)}</s>
          )}
        </p>
        <div className="hero-slide-actions">
          {product.available && (
            <button
              className="primary-button"
              disabled={pending}
              onClick={() => add(product.id, Math.max(1, product.min_order_qty), "/")}
              type="button"
            >
              {pending ? "…" : t("carousel.add_to_cart")}
            </button>
          )}
          <Link className="secondary-button hero-details-link" to={detail}>
            {t("carousel.details")}
            <span aria-hidden="true">→</span>
          </Link>
        </div>
      </div>
      <Link aria-hidden="true" className="hero-slide-visual" tabIndex={-1} to={detail}>
        <span className="hero-slide-halo" />
        {product.image_url ? (
          <img alt="" decoding="async" src={product.image_url} />
        ) : (
          <StationeryArt className="hero-product-art" variant={`${product.name_uz}`} />
        )}
      </Link>
    </div>
  );
}

function Chevron({ direction }: { direction: "left" | "right" }) {
  return (
    <svg aria-hidden="true" className="size-5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24">
      <path d={direction === "left" ? "m15 5-7 7 7 7" : "m9 5 7 7-7 7"} />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="currentColor" viewBox="0 0 24 24">
      <rect height="14" rx="1.5" width="4" x="6" y="5" />
      <rect height="14" rx="1.5" width="4" x="14" y="5" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="currentColor" viewBox="0 0 24 24">
      <path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" />
    </svg>
  );
}
