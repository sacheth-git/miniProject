import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { homeFor, useAuth } from "../lib/auth";
import type { User } from "../lib/api";
import { Spinner } from "./ui";

/** Route guard: signed in, password set, and (optionally) one of `roles`. */
export function RequireAuth({ roles, children }: { roles?: User["role"][]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <div className="p-8"><Spinner /></div>;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  if (user.must_reset_password && loc.pathname !== "/change-password") return <Navigate to="/change-password" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to={homeFor(user)} replace />;
  return <>{children}</>;
}
