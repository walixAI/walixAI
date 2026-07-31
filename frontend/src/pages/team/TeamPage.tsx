import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Eye, EyeOff, Lock, Loader2, Pencil, UserPlus } from "lucide-react";
import { api, type TeamMemberOut } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { TeamPerformanceTab } from "@/components/team/TeamPerformanceTab";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

// ── Role config ────────────────────────────────────────────────────────────────

const ROLE_CONFIG: Record<string, { label: string; className: string }> = {
  owner:   { label: "Owner",    className: "bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-950 dark:text-purple-300" },
  it:      { label: "IT",       className: "bg-slate-100  text-slate-700  border-slate-200  dark:bg-slate-800  dark:text-slate-300"  },
  gerente: { label: "Gerente",  className: "bg-blue-100   text-blue-700   border-blue-200   dark:bg-blue-950   dark:text-blue-300"   },
  doctor:  { label: "Doctor",   className: "bg-green-100  text-green-700  border-green-200  dark:bg-green-950  dark:text-green-300"  },
  asesor:  { label: "Asesor",   className: "bg-amber-100  text-amber-700  border-amber-200  dark:bg-amber-950  dark:text-amber-300"  },
  soporte: { label: "Soporte",  className: "bg-slate-100  text-slate-600  border-slate-200  dark:bg-slate-800  dark:text-slate-400"  },
};

const ASSIGNABLE_ROLES = ["asesor", "gerente", "doctor"] as const;

function RoleBadge({ role }: { role: string }) {
  const cfg = ROLE_CONFIG[role] ?? { label: role, className: "" };
  return (
    <Badge variant="outline" className={cn("text-xs font-medium", cfg.className)}>
      {cfg.label}
    </Badge>
  );
}

// ── Avatar ─────────────────────────────────────────────────────────────────────

const AVATAR_COLORS = [
  "bg-violet-500", "bg-blue-500", "bg-teal-500",
  "bg-green-500", "bg-amber-500", "bg-rose-500",
];

function Avatar({ name }: { name: string }) {
  const idx = name.charCodeAt(0) % AVATAR_COLORS.length;
  return (
    <div
      className={cn(
        "h-8 w-8 rounded-full flex items-center justify-center text-sm font-semibold text-white shrink-0",
        AVATAR_COLORS[idx],
      )}
      aria-hidden="true"
    >
      {name.charAt(0).toUpperCase()}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function TeamPage() {
  const { user } = useAuth();
  const branchId = user?.branch_id ?? "";
  const isOwner = user?.role === "owner";
  const canViewPerformance =
    user?.role === "owner" || user?.role === "platform_owner";
  const queryClient = useQueryClient();

  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get("tab") ?? "members") as "members" | "performance";
  function setTab(tab: string) { setSearchParams({ tab }); }

  const [showAdd, setShowAdd] = useState(false);
  const [editTarget, setEditTarget] = useState<TeamMemberOut | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<TeamMemberOut | null>(null);

  const { data: team = [], isLoading } = useQuery({
    queryKey: ["team", branchId],
    queryFn: () => api.getTeam(branchId),
    enabled: !!branchId,
  });

  const toggleMutation = useMutation({
    mutationFn: (userId: string) => api.toggleUser(userId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["team", branchId] }),
    onError: (e: Error) =>
      toast.error("No se pudo cambiar el estado", { description: e.message }),
  });

  function handleSwitchClick(member: TeamMemberOut) {
    if (member.is_active) {
      setDeactivateTarget(member);
    } else {
      toggleMutation.mutate(member.id);
    }
  }

  if (!branchId) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-muted-foreground">
          Tu cuenta no está asignada a ninguna sucursal.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Equipo</h1>
          <p className="text-sm text-muted-foreground">Usuarios de esta sucursal</p>
        </div>
        {isOwner && activeTab === "members" && (
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <UserPlus className="h-4 w-4 mr-2" />
            Agregar usuario
          </Button>
        )}
      </div>

      <Tabs value={activeTab} onValueChange={setTab} className="space-y-5">
        <TabsList>
          <TabsTrigger value="members">Miembros</TabsTrigger>
          <TabsTrigger value="performance">Rendimiento</TabsTrigger>
        </TabsList>

        {/* ── Members tab ─────────────────────────────────────────────────── */}
        <TabsContent value="members" className="space-y-5">
          <div className="rounded-xl border bg-card overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12" />
                  <TableHead>Nombre</TableHead>
                  <TableHead>Rol</TableHead>
                  <TableHead className="hidden sm:table-cell">Teléfono WA</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow>
                    <TableCell colSpan={6} className="h-32 text-center">
                      <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
                    </TableCell>
                  </TableRow>
                ) : team.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="h-32 text-center text-sm text-muted-foreground">
                      No hay usuarios en esta sucursal.
                    </TableCell>
                  </TableRow>
                ) : (
                  team.map((member) => (
                    <TableRow
                      key={member.id}
                      className={cn(!member.is_active && "opacity-50")}
                    >
                      <TableCell>
                        <Avatar name={member.name} />
                      </TableCell>
                      <TableCell>
                        <div>
                          <p className="font-medium text-sm leading-tight">{member.name}</p>
                          <p className="text-xs text-muted-foreground">{member.email}</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <RoleBadge role={member.role} />
                      </TableCell>
                      <TableCell className="hidden sm:table-cell text-sm text-muted-foreground">
                        {member.wa_phone ?? "—"}
                      </TableCell>
                      <TableCell>
                        <Switch
                          checked={member.is_active}
                          onCheckedChange={() => handleSwitchClick(member)}
                          disabled={!isOwner || toggleMutation.isPending}
                          aria-label={member.is_active ? "Desactivar" : "Activar"}
                        />
                      </TableCell>
                      <TableCell>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          onClick={() => setEditTarget(member)}
                          aria-label={`Editar ${member.name}`}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        {/* ── Performance tab ──────────────────────────────────────────────── */}
        <TabsContent value="performance">
          {canViewPerformance ? (
            <TeamPerformanceTab />
          ) : (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <div className="rounded-full bg-muted p-4">
                <Lock className="h-6 w-6 text-muted-foreground" />
              </div>
              <div>
                <p className="text-sm font-semibold">Acceso restringido</p>
                <p className="text-xs text-muted-foreground mt-0.5 max-w-xs">
                  Solo el propietario puede ver el rendimiento del equipo.
                </p>
              </div>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Dialogs — fuera de Tabs ya que son portals */}
      {showAdd && (
        <AddUserDialog
          branchId={branchId}
          onClose={() => setShowAdd(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["team", branchId] });
            setShowAdd(false);
          }}
        />
      )}

      {editTarget && (
        <EditUserDialog
          member={editTarget}
          isOwner={isOwner}
          onClose={() => setEditTarget(null)}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ["team", branchId] });
            setEditTarget(null);
          }}
        />
      )}

      <AlertDialog
        open={!!deactivateTarget}
        onOpenChange={(open) => !open && setDeactivateTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              ¿Desactivar a {deactivateTarget?.name}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Ya no podrá entrar al sistema. Puedes reactivarlo en cualquier momento.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={toggleMutation.isPending}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive hover:bg-destructive/90 focus:ring-destructive"
              disabled={toggleMutation.isPending}
              onClick={() => {
                if (deactivateTarget) {
                  toggleMutation.mutate(deactivateTarget.id, {
                    onSettled: () => setDeactivateTarget(null),
                  });
                }
              }}
            >
              {toggleMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                "Desactivar"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ── Add user dialog ────────────────────────────────────────────────────────────

function AddUserDialog({
  branchId,
  onClose,
  onCreated,
}: {
  branchId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [role, setRole] = useState<string>("asesor");
  const [waPhone, setWaPhone] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      api.createTeamMember(branchId, {
        name: name.trim(),
        email: email.trim(),
        password,
        role,
        wa_phone: waPhone.trim() || null,
      }),
    onSuccess: () => {
      toast.success(`${name.trim()} agregado al equipo`);
      onCreated();
    },
    onError: (e: Error) =>
      toast.error("No se pudo agregar", { description: e.message }),
  });

  const canSubmit =
    name.trim().length > 0 &&
    email.trim().length > 0 &&
    password.length >= 8 &&
    !mutation.isPending;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Agregar usuario</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <Field label="Nombre completo" htmlFor="add-name">
            <Input
              id="add-name"
              placeholder="Ej. María González"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>

          <Field label="Email" htmlFor="add-email">
            <Input
              id="add-email"
              type="email"
              placeholder="usuario@empresa.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>

          <Field label="Contraseña temporal" htmlFor="add-pwd">
            <div className="relative">
              <Input
                id="add-pwd"
                type={showPwd ? "text" : "password"}
                placeholder="Mínimo 8 caracteres"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPwd((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                tabIndex={-1}
                aria-label={showPwd ? "Ocultar contraseña" : "Mostrar contraseña"}
              >
                {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </Field>

          <Field label="Rol" htmlFor="add-role">
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger id="add-role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ASSIGNABLE_ROLES.map((r) => (
                  <SelectItem key={r} value={r}>
                    {ROLE_CONFIG[r]?.label ?? r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field label="Teléfono WhatsApp" htmlFor="add-phone">
            <Input
              id="add-phone"
              placeholder="+52XXXXXXXXXX"
              value={waPhone}
              onChange={(e) => setWaPhone(e.target.value)}
            />
          </Field>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => mutation.mutate()} disabled={!canSubmit}>
            {mutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <UserPlus className="h-4 w-4 mr-2" />
            )}
            Agregar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Edit user dialog ───────────────────────────────────────────────────────────

function EditUserDialog({
  member,
  isOwner,
  onClose,
  onSaved,
}: {
  member: TeamMemberOut;
  isOwner: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(member.name);
  const [role, setRole] = useState(member.role);
  const [waPhone, setWaPhone] = useState(member.wa_phone ?? "");

  const mutation = useMutation({
    mutationFn: () =>
      api.updateUser(member.id, {
        name: name.trim(),
        wa_phone: waPhone.trim() || null,
        ...(isOwner ? { role } : {}),
      }),
    onSuccess: () => {
      toast.success("Usuario actualizado");
      onSaved();
    },
    onError: (e: Error) =>
      toast.error("No se pudo actualizar", { description: e.message }),
  });

  const canSubmit = name.trim().length > 0 && !mutation.isPending;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Editar usuario</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <Field label="Nombre completo" htmlFor="edit-name">
            <Input
              id="edit-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>

          {isOwner && (
            <Field label="Rol" htmlFor="edit-role">
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger id="edit-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ASSIGNABLE_ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {ROLE_CONFIG[r]?.label ?? r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          )}

          <Field label="Teléfono WhatsApp" htmlFor="edit-phone">
            <Input
              id="edit-phone"
              placeholder="+52XXXXXXXXXX"
              value={waPhone}
              onChange={(e) => setWaPhone(e.target.value)}
            />
          </Field>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => mutation.mutate()} disabled={!canSubmit}>
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Field wrapper ──────────────────────────────────────────────────────────────

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}
