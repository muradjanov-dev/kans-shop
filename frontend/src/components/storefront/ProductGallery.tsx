import { useEffect, useRef, useState } from "react";
import { useTranslate } from "@/lib/i18n";
import type { ProductImage } from "@/types/api";

export function ProductGallery({ images, name }: { images: ProductImage[]; name: string }) {
  const t = useTranslate();
  const validImages = images.filter((image) => Boolean(image.url?.trim()));
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [failedImageIds, setFailedImageIds] = useState<Set<number>>(() => new Set());
  const touchStartX = useRef<number | null>(null);
  const selectedImage = validImages[selectedIndex];
  const selectedFailed = selectedImage ? failedImageIds.has(selectedImage.id) : false;

  useEffect(() => {
    setSelectedIndex(0);
    setFailedImageIds(new Set());
  }, [images]);

  function markFailed(imageId: number): void {
    setFailedImageIds((current) => new Set(current).add(imageId));
  }

  function selectNext(direction: -1 | 1): void {
    if (validImages.length < 2) return;
    setSelectedIndex((current) => (current + direction + validImages.length) % validImages.length);
  }

  return (
    <section
      aria-label={t("product.image_gallery")}
      className="flex min-w-0 flex-col gap-3"
      onTouchEnd={(event) => {
        const startX = touchStartX.current;
        const endX = event.changedTouches[0]?.clientX;
        touchStartX.current = null;
        if (startX === null || endX === undefined || Math.abs(endX - startX) < 40) return;
        selectNext(endX < startX ? 1 : -1);
      }}
      onTouchStart={(event) => {
        touchStartX.current = event.touches[0]?.clientX ?? null;
      }}
    >
      <div className="flex aspect-square w-full items-center justify-center overflow-hidden rounded-2xl bg-slate-100 dark:bg-slate-800">
        {selectedImage && !selectedFailed ? (
          <img
            alt={name}
            className="size-full object-contain"
            onError={() => markFailed(selectedImage.id)}
            src={selectedImage.url?.trim()}
          />
        ) : (
          <ImageFallback label={t("product.image_unavailable")} />
        )}
      </div>
      {validImages.length > 1 && (
        <div aria-label={t("product.image_gallery")} className="flex gap-2 overflow-x-auto pb-1">
          {validImages.map((image, index) => {
            const failed = failedImageIds.has(image.id);
            const label = t("product.select_image", { number: index + 1 });
            return (
              <button
                aria-label={label}
                aria-pressed={index === selectedIndex}
                className={`flex size-16 min-h-11 min-w-11 shrink-0 items-center justify-center overflow-hidden rounded-xl border-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
                  index === selectedIndex ? "border-brand" : "border-transparent"
                }`}
                key={image.id}
                onClick={() => setSelectedIndex(index)}
                type="button"
              >
                {failed ? (
                  <span aria-hidden="true" className="size-full bg-slate-200 dark:bg-slate-700" />
                ) : (
                  <img
                    alt=""
                    className="size-full bg-slate-100 object-cover dark:bg-slate-800"
                    loading="lazy"
                    onError={() => markFailed(image.id)}
                    src={image.url?.trim()}
                  />
                )}
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ImageFallback({ label }: { label: string }) {
  return (
    <span
      aria-label={label}
      className="flex size-full items-center justify-center bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500"
      role="img"
    >
      <span aria-hidden="true" className="size-16 rounded-2xl border-2 border-current opacity-40" />
    </span>
  );
}
