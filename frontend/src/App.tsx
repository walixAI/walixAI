import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useInitAuth, useAuth } from "@/hooks/useAuth";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { ErrorBoundary } from "@/components/walix/ErrorBoundary";
import { LoadingSpinner } from "@/components/walix/LoadingSpinner";
import { Stub } from "@/pages/app/Stub";
import { Users, BarChart3, Settings } from "lucide-react";

// Eager: critical
import Login from "@/pages/Login";
import NotFound from "@/pages/NotFound";

// Lazy: heavy pages
const PlatformDashboard = lazy(() => import("@/pages/platform/PlatformDashboard"));
const Dashboard = lazy(() => import("@/pages/dashboard/DashboardPage"));
const Whatsapp = lazy(() => import("@/pages/app/Whatsapp"));
const SettingsPage = lazy(() => import("@/pages/app/Settings"));
const PipelinePage = lazy(() => import("@/pages/app/Pipeline"));
const OnboardingWizard = lazy(() => import("@/pages/onboarding/OnboardingWizard"));
const PreviewPage = lazy(() => import("@/pages/onboarding/PreviewPage"));
const TeamPage = lazy(() => import("@/pages/team/TeamPage"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      staleTime: 30_000,
    },
  },
});

function RouteFallback() {
  return (
    <div className="min-h-[40vh] flex items-center justify-center" role="status" aria-label="Cargando">
      <LoadingSpinner />
    </div>
  );
}

// Redirects / based on user role after auth resolves
function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <RouteFallback />;
  if (user?.role === "platform_owner") return <Navigate to="/platform" replace />;
  return <Navigate to="/dashboard" replace />;
}

// Guards /platform — only platform_owner may enter
function PlatformRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <RouteFallback />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "platform_owner") return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

const AppRoutes = () => {
  useInitAuth();
  return (
    <ErrorBoundary>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<Login />} />

          {/* Root redirect — role-aware */}
          <Route path="/" element={<RootRedirect />} />

          {/* Protected app layout */}
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/whatsapp" element={<Whatsapp />} />
            <Route
              path="/contacts"
              element={
                <Stub
                  icon={Users}
                  title="Contactos"
                  description="Gestion de contactos proximamente."
                  badge="Proximo"
                />
              }
            />
            <Route
              path="/reports"
              element={
                <Stub
                  icon={BarChart3}
                  title="Reportes"
                  description="Reportes y analiticas proximamente."
                  badge="Proximo"
                />
              }
            />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/settings/team" element={<TeamPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
          </Route>

          {/* Onboarding flow — protected, no AppLayout */}
          <Route
            path="/onboarding/new"
            element={
              <ProtectedRoute>
                <OnboardingWizard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/onboarding/preview/:draftId"
            element={
              <ProtectedRoute>
                <PreviewPage />
              </ProtectedRoute>
            }
          />

          {/* Platform Owner — standalone, no AppLayout */}
          <Route
            path="/platform"
            element={
              <PlatformRoute>
                <PlatformDashboard />
              </PlatformRoute>
            }
          />

          {/* 404 */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
