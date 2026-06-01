import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { BottomNav } from "./BottomNav";
import { ImpersonationBanner } from "./ImpersonationBanner";
import { WalixAIBar } from "@/components/ai/WalixAIBar";

export function AppLayout() {
  return (
    <div className="min-h-screen w-full flex flex-col bg-background">
      <ImpersonationBanner />
      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <TopBar />
          {/* pb-36 mobile: BottomNav (h-16) + AIBar (h-14) + gap; md:pb-20 desktop: AIBar only */}
          <main className="flex-1 px-4 md:px-6 py-6 pb-36 md:pb-20">
            <Outlet />
          </main>
        </div>
      </div>
      <BottomNav />
      <WalixAIBar />
    </div>
  );
}
