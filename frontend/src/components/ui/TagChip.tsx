import type { TagRow } from "@/lib/queries/contacts";

interface TagChipProps {
  tag: TagRow;
  onRemove?: () => void;
}

export function TagChip({ tag, onRemove }: TagChipProps) {
  const color = tag.color ?? "#6366f1";
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border leading-none"
      style={{
        backgroundColor: `${color}20`,
        borderColor: `${color}60`,
        color,
      }}
    >
      {tag.name}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="hover:opacity-70 leading-none"
          aria-label={`Quitar ${tag.name}`}
        >
          ×
        </button>
      )}
    </span>
  );
}
