import { useEffect, useState } from "react";
import { localizedField } from "@/lib/format";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import type { Category } from "@/types/api";

export function CategoryTile({
  category,
  selected = false,
  onSelect,
}: {
  category: Category;
  selected?: boolean;
  onSelect: (category: Category) => void;
}) {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const [imageFailed, setImageFailed] = useState(false);
  const name = localizedField(language, category, "name");
  const imageUrl = category.image_url?.trim();

  useEffect(() => setImageFailed(false), [imageUrl]);

  return (
    <button
      aria-current={selected ? "true" : undefined}
      className={`group flex min-h-11 min-w-0 items-center gap-3 rounded-2xl border p-3 text-left shadow-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
        selected
          ? "border-brand bg-violet-50 text-violet-900 dark:bg-violet-400/15 dark:text-violet-100"
          : "border-slate-200 bg-white text-slate-900 hover:border-violet-300 dark:border-white/10 dark:bg-slate-900 dark:text-white"
      }`}
      onClick={() => onSelect(category)}
      type="button"
    >
      <span className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-800">
        {imageUrl && !imageFailed ? (
          <img
            alt=""
            className="size-full object-cover"
            loading="lazy"
            onError={() => setImageFailed(true)}
            src={imageUrl}
          />
        ) : (
          <span
            aria-label={t("catalog.category_image_unavailable")}
            className="flex size-full items-center justify-center bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500"
            role="img"
          >
            <span aria-hidden="true" className="size-7 rounded-lg border-2 border-current opacity-40" />
          </span>
        )}
      </span>
      <span className="min-w-0 flex-1 text-sm font-semibold">{name}</span>
    </button>
  );
}
