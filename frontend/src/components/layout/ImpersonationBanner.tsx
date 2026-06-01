import { useNavigate } from "react-router-dom";
import { ShieldAlert, LogOut } from "lucide-react";
import { endImpersonation, getImpersonatedTenantName, isImpersonating } from "@/lib/api";

export function ImpersonationBanner() {
  const navigate = useNavigate();

  if (!isImpersonating()) return null;

  const tenantName = getImpersonatedTenantName() ?? "este cliente";

  const handleExit = () => {
    endImpersonation();
    navigate("/platform");
  };

  return (
    <div className="w-full bg-orange-500 text-white px-4 py-2.5 flex items-center gap-3 z-50 shrink-0">
      <ShieldAlert className="h-4 w-4 shrink-0" />
      <p className="text-xs flex-1 font-medium">
        Estás viendo la cuenta de{" "}
        <strong className="font-bold">{tenantName}</strong>{" "}
        en modo solo lectura. Todo lo que hagas queda registrado.
      </p>
      <button
        onClick={handleExit}
        className="flex items-center gap-1.5 text-xs font-semibold shrink-0
                   bg-white/20 hover:bg-white/30 transition-colors rounded-md px-2.5 py-1"
      >
        <LogOut className="h-3.5 w-3.5" />
        Salir
      </button>
    </div>
  );
}
