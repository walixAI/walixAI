import React from "react";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";
import { Button } from "@/components/ui/button";

interface State {
  hasError: boolean;
  error?: Error;
}

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("[Walix ErrorBoundary]", error, info);
  }

  reset = () => this.setState({ hasError: false, error: undefined });

  render() {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback) return this.props.fallback;

    return (
      <div
        role="alert"
        className="min-h-[60vh] flex flex-col items-center justify-center text-center px-6 animate-fade-in"
      >
        <div className="h-14 w-14 rounded-2xl bg-danger/10 grid place-items-center mb-4">
          <AlertTriangle className="h-7 w-7 text-danger" aria-hidden="true" />
        </div>
        <h2 className="text-xl font-semibold">Ups! Algo salio mal</h2>
        <p className="mt-1 text-sm text-muted-foreground max-w-md">
          Se produjo un error inesperado. Puedes recargar la pagina o volver al dashboard.
        </p>
        {this.state.error?.message && (
          <code className="mt-3 text-[11px] text-muted-foreground bg-muted/50 rounded px-2 py-1 max-w-md truncate">
            {this.state.error.message}
          </code>
        )}
        <div className="mt-5 flex gap-2">
          <Button onClick={() => window.location.reload()} aria-label="Recargar pagina">
            <RefreshCw className="h-4 w-4 mr-1.5" /> Recargar
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              this.reset();
              window.location.href = "/dashboard";
            }}
            aria-label="Ir al dashboard"
          >
            <Home className="h-4 w-4 mr-1.5" /> Dashboard
          </Button>
        </div>
      </div>
    );
  }
}
