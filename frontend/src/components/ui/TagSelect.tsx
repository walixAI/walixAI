import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { TagChip } from "@/components/ui/TagChip";
import { getTags, createTag } from "@/lib/queries/tags";
import type { TagRow } from "@/lib/queries/contacts";

interface TagSelectProps {
  value: TagRow[];
  onChange: (tags: TagRow[]) => void;
}

export function TagSelect({ value, onChange }: TagSelectProps) {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [showList, setShowList] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data: allTags = [] } = useQuery({
    queryKey: ["tags"],
    queryFn: getTags,
    staleTime: 5 * 60_000,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createTag(name),
    onSuccess: (newTag) => {
      qc.invalidateQueries({ queryKey: ["tags"] });
      onChange([...value, newTag]);
      setQuery("");
    },
  });

  const filtered = allTags.filter(
    (t) =>
      !value.some((v) => v.id === t.id) &&
      t.name.toLowerCase().includes(query.toLowerCase()),
  );

  const addTag = (tag: TagRow) => {
    onChange([...value, tag]);
    setQuery("");
    inputRef.current?.focus();
  };

  const removeTag = (id: string) => {
    onChange(value.filter((t) => t.id !== id));
  };

  // Close dropdown on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setShowList(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  const canCreate = query.trim().length > 0 && !allTags.some((t) => t.name.toLowerCase() === query.toLowerCase().trim());

  return (
    <div ref={containerRef} className="space-y-1.5">
      {/* Current tags */}
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((tag) => (
            <TagChip key={tag.id} tag={tag} onRemove={() => removeTag(tag.id)} />
          ))}
        </div>
      )}

      {/* Search input */}
      <div className="relative">
        <Input
          ref={inputRef}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setShowList(true); }}
          onFocus={() => setShowList(true)}
          placeholder="Buscar o crear etiqueta…"
          className="h-7 text-xs pr-6"
        />
        {createMutation.isPending && (
          <Loader2 className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 animate-spin text-muted-foreground" />
        )}
      </div>

      {/* Dropdown */}
      {showList && (filtered.length > 0 || canCreate) && (
        <div className="absolute z-50 mt-0.5 w-48 rounded-md border border-border bg-popover shadow-md py-1">
          {filtered.map((tag) => (
            <button
              key={tag.id}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); addTag(tag); }}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-muted flex items-center gap-2"
            >
              <span
                className="h-2 w-2 rounded-full shrink-0"
                style={{ backgroundColor: tag.color ?? "#6366f1" }}
              />
              {tag.name}
            </button>
          ))}
          {canCreate && (
            <button
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                createMutation.mutate(query.trim());
              }}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-muted flex items-center gap-1.5 text-primary font-medium"
            >
              <Plus className="h-3 w-3" />
              Crear "{query.trim()}"
            </button>
          )}
        </div>
      )}
    </div>
  );
}
