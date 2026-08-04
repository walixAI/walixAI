import { useAuth } from "@/hooks/useAuth";
import { RunRateCard } from "@/components/walix/RunRateCard";
import { ProfitabilityCard } from "@/components/walix/ProfitabilityCard";

export function RunRateProfitabilityRow() {
  const { user } = useAuth();
  const canSeeTeam =
    user?.role === "owner" ||
    user?.role === "platform_owner" ||
    user?.role === "gerente";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <RunRateCard compact showSellers={canSeeTeam} />
      <ProfitabilityCard />
    </div>
  );
}
