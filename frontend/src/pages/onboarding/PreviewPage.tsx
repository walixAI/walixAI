import { useParams } from "react-router-dom";
import { Logo } from "@/components/walix/Logo";

export default function PreviewPage() {
  const { draftId } = useParams<{ draftId: string }>();
  void draftId; // will be used when T-33 implements the preview

  return (
    <div className="min-h-screen bg-muted/30 flex flex-col">
      <header className="h-14 shrink-0 border-b bg-background flex items-center px-6">
        <Logo collapsed={false} />
      </header>
      <main className="flex-1 flex items-center justify-center">
        <p className="text-muted-foreground text-sm">Vista previa del draft — próximamente.</p>
      </main>
    </div>
  );
}
