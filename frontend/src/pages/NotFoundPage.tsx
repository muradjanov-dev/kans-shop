import { Link } from "react-router-dom";
import { useTranslate } from "@/lib/i18n";

export function NotFoundPage() {
  const t = useTranslate();
  return <div className="page-shell"><div className="empty-state"><h1 className="page-title">{t("page.not_found")}</h1><Link className="primary-button mt-4" to="/">{t("page.back_catalog")}</Link></div></div>;
}
