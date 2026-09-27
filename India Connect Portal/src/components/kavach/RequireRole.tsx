import { Navigate } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useAuth, type Role } from "@/lib/auth";
import { Loader2 } from "lucide-react";

export function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, ready } = useAuth();

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-hero text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    );
  }

  if (!user) {
    const redirect = typeof window !== "undefined" ? window.location.pathname : "/";
    return <Navigate to="/auth" search={{ role, mode: "login", redirect }} replace />;
  }

  if (user.role !== role) {
    // Signed in but wrong role — send to their correct dashboard
    return <Navigate to={user.role === "official" ? "/official" : "/public"} replace />;
  }

  return <>{children}</>;
}
