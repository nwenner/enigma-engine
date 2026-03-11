import { useState, useRef } from "react";

interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  suggestions: string[];
  placeholder?: string;
}

export function TagInput({ tags, onChange, suggestions, placeholder }: TagInputProps) {
  const [input, setInput] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = suggestions.filter(
    (s) =>
      input.length > 0 &&
      s.toLowerCase().includes(input.toLowerCase()) &&
      !tags.includes(s)
  );

  function addTag(raw: string) {
    const tag = raw.trim();
    if (tag && !tags.includes(tag)) {
      onChange([...tags, tag]);
    }
    setInput("");
    setOpen(false);
  }

  function removeTag(tag: string) {
    onChange(tags.filter((t) => t !== tag));
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "," || e.key === "Enter") {
      e.preventDefault();
      if (input.trim()) addTag(input);
    } else if (e.key === "Backspace" && input === "" && tags.length > 0) {
      removeTag(tags[tags.length - 1]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="relative">
      <div
        className="flex flex-wrap gap-1.5 bg-d2bg-elevated border border-d2border rounded px-2 py-1.5 min-h-[36px] cursor-text focus-within:border-d2gold/50 transition-colors"
        onClick={() => inputRef.current?.focus()}
      >
        {tags.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 bg-d2gold/15 border border-d2gold/30 text-d2gold text-xs rounded px-2 py-0.5"
          >
            {tag}
            <button
              type="button"
              className="text-d2gold/50 hover:text-d2gold leading-none"
              onClick={(e) => {
                e.stopPropagation();
                removeTag(tag);
              }}
            >
              ×
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          className="flex-1 min-w-[100px] bg-transparent text-sm text-slate-100 placeholder-slate-600 focus:outline-none"
          value={input}
          placeholder={tags.length === 0 ? placeholder : ""}
          onChange={(e) => {
            setInput(e.target.value);
            setOpen(true);
          }}
          onKeyDown={handleKeyDown}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
        />
      </div>

      {open && filtered.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-d2bg-card border border-d2border rounded shadow-lg z-10 max-h-44 overflow-y-auto">
          {filtered.map((s) => (
            <button
              key={s}
              type="button"
              className="w-full text-left px-3 py-1.5 text-sm text-slate-300 hover:bg-d2bg-elevated hover:text-d2gold transition-colors"
              onMouseDown={() => addTag(s)}
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
