import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { startAnalytics, trackPage } from "@/lib/analytics";

/** Starts storefront analytics and reports each page (not each filter change) once. */
export function AnalyticsTracker() {
  const { pathname } = useLocation();

  useEffect(() => {
    const tracker = startAnalytics();
    return () => tracker?.pause();
  }, []);

  useEffect(() => {
    trackPage(pathname);
  }, [pathname]);

  return null;
}
