import { useState } from "react";
import { AlignLeft, LayoutList } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";

interface ContactDetailLayoutProps {
  leftPanel: React.ReactNode;
  center: React.ReactNode;
  rightPanel: React.ReactNode;
}

export function ContactDetailLayout({
  leftPanel,
  center,
  rightPanel,
}: ContactDetailLayoutProps) {
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  return (
    <>
      {/* Mobile: show panel toggles + center only */}
      <div className="md:hidden">
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border">
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1 text-xs"
            onClick={() => setLeftOpen(true)}
          >
            <AlignLeft className="h-3.5 w-3.5" />
            Datos
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1 text-xs"
            onClick={() => setRightOpen(true)}
          >
            <LayoutList className="h-3.5 w-3.5" />
            Deals y IA
          </Button>
        </div>
        <div className="overflow-auto">{center}</div>
      </div>

      {/* Desktop: 3-column grid */}
      <div
        className="hidden md:grid h-full overflow-hidden"
        style={{ gridTemplateColumns: "256px 1fr 256px" }}
      >
        {/* Left panel */}
        <div data-testid="contact-left-panel" className="border-r border-border overflow-y-auto">
          <div className="sticky top-0">{leftPanel}</div>
        </div>

        {/* Center */}
        <div data-testid="contact-center" className="overflow-y-auto p-5">{center}</div>

        {/* Right panel */}
        <div data-testid="contact-right-panel" className="border-l border-border overflow-y-auto">
          <div className="sticky top-0">{rightPanel}</div>
        </div>
      </div>

      {/* Mobile sheets */}
      <Sheet open={leftOpen} onOpenChange={setLeftOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="px-4 py-3 border-b border-border">
            <SheetTitle className="text-sm">Datos del contacto</SheetTitle>
          </SheetHeader>
          <div className="overflow-y-auto">{leftPanel}</div>
        </SheetContent>
      </Sheet>

      <Sheet open={rightOpen} onOpenChange={setRightOpen}>
        <SheetContent side="right" className="w-72 p-0">
          <SheetHeader className="px-4 py-3 border-b border-border">
            <SheetTitle className="text-sm">Deals y sugerencias</SheetTitle>
          </SheetHeader>
          <div className="overflow-y-auto">{rightPanel}</div>
        </SheetContent>
      </Sheet>
    </>
  );
}
