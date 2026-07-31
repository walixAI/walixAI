import { GoalsListCard } from "./GoalsListCard";
import { ProductCategoriesCard } from "./ProductCategoriesCard";
import { ProfitThresholdsCard } from "./ProfitThresholdsCard";

export function GoalsTab() {
  return (
    <div className="space-y-8">
      <GoalsListCard />
      <div className="border-t border-border pt-6">
        <ProductCategoriesCard />
      </div>
      <div className="border-t border-border pt-6">
        <ProfitThresholdsCard />
      </div>
    </div>
  );
}
