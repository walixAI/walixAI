const AVATAR_COLORS = [
  "#7C3AED", "#0891B2", "#059669", "#D97706",
  "#DC2626", "#DB2777", "#2563EB", "#0D9488",
];

function hashColor(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = id.charCodeAt(i) + ((h << 5) - h);
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
}

interface ContactAvatarProps {
  id: string;
  name: string | null;
  lastName?: string | null;
  avatarUrl?: string | null;
  size?: "sm" | "md" | "lg";
}

const SIZE_CLASSES = {
  sm:  "h-7 w-7 text-[10px]",
  md:  "h-9 w-9 text-xs",
  lg:  "h-12 w-12 text-sm",
};

export function ContactAvatar({ id, name, lastName, avatarUrl, size = "md" }: ContactAvatarProps) {
  const initials = [name, lastName]
    .filter(Boolean)
    .map((s) => s!.charAt(0).toUpperCase())
    .join("")
    .slice(0, 2) || "?";

  const sizeClass = SIZE_CLASSES[size];

  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={name ?? "avatar"}
        className={`${sizeClass} rounded-full object-cover shrink-0`}
      />
    );
  }

  return (
    <span
      className={`${sizeClass} inline-flex items-center justify-center rounded-full font-bold text-white shrink-0`}
      style={{ backgroundColor: hashColor(id) }}
      aria-label={name ?? "Contacto"}
    >
      {initials}
    </span>
  );
}
