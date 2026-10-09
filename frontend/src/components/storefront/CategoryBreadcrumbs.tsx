import { useMemo } from "react";
import { localizedField } from "@/lib/format";
import { useTranslate } from "@/lib/i18n";
import { useLanguageStore } from "@/store/language";
import type { Category } from "@/types/api";

export function CategoryBreadcrumbs({
  categories,
  categoryId,
  onSelect,
}: {
  categories: Category[];
  categoryId: number | null;
  onSelect: (categoryId: number | null) => void;
}) {
  const t = useTranslate();
  const language = useLanguageStore((state) => state.language);
  const path = useMemo(() => {
    const byId = new Map(categories.map((category) => [category.id, category]));
    const result: Category[] = [];
    const visited = new Set<number>();
    let current = categoryId === null ? undefined : byId.get(categoryId);

    while (current && !visited.has(current.id)) {
      visited.add(current.id);
      result.unshift(current);
      current = current.parent_id === null ? undefined : byId.get(current.parent_id);
    }
    return result;
  }, [categories, categoryId]);

  if (categoryId === null) return null;

  return (
    <nav aria-label={t("catalog.categories")} className="mb-4 overflow-x-auto">
      <ol className="flex min-h-11 min-w-max items-center gap-2 text-sm">
        <li>
          <button
            className="min-h-11 rounded-lg px-2 font-medium text-brand underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            onClick={() => onSelect(null)}
            type="button"
          >
            {t("catalog.all_categories")}
          </button>
        </li>
        {path.map((category, index) => {
          const current = index === path.length - 1;
          return (
            <li className="flex items-center gap-2" key={category.id}>
              <span aria-hidden="true" className="text-slate-400">/</span>
              {current ? (
                <span aria-current="page" className="max-w-48 truncate font-semibold text-slate-700 dark:text-slate-200">
                  {localizedField(language, category, "name")}
                </span>
              ) : (
                <button
                  className="min-h-11 rounded-lg px-2 font-medium text-brand underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                  onClick={() => onSelect(category.id)}
                  type="button"
                >
                  {localizedField(language, category, "name")}
                </button>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
