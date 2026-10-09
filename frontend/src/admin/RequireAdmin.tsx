import { Navigate, useLocation } from "react-router-dom";
import { useTranslate } from "@/lib/i18n";
import { useAdminAuth } from "@/admin/AdminAuthProvider";
import type { AdminRole } from "@/admin/api";

interface RequireAdminProps {
  children: React.ReactNode;
  roles?: readonly AdminRole[];
}

export function RequireAdmin({ children, roles }: RequireAdminProps) {
  const { session, status } = useAdminAuth();
  const location = useLocation();
  const t = useTranslate();

  if (status === "checking") {
    return <p className="p-6 text-center text-sm" role="status">{t("admin.loading_session")}</p>;
  }
  if (status !== "authenticated" || !session) {
    return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />;
  }
  if (roles && !roles.includes(session.role)) {
    return <Navigate to="/admin" replace />;
  }
  return children;
}
