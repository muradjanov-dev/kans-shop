import { Link } from "react-router-dom";
import { useLanguageStore } from "@/store/language";
import { useTranslate } from "@/lib/i18n";
import { localizedField } from "@/lib/format";
import type { Category } from "@/types/api";

export function CategoryCard({ category }: { category: Category }) {
  const language = useLanguageStore((state) => state.language);
  const t = useTranslate();
  const name = localizedField(language, category, "name");

  return (
    <Link
      to={`/?category=${category.id}`}
      className="flex flex-col items-center gap-2 rounded-xl border border-gray-100 bg-white p-4 text-center shadow-sm"
    >
      <span className="text-2xl">🗂️</span>
      <span className="text-sm font-medium text-gray-900">{name}</span>
      <span className="text-xs text-gray-500">
        {t("catalog.products_count", { count: category.products_count })}
      </span>
    </Link>
  );
}
