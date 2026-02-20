interface Props {
  open: boolean;
  children: React.ReactNode;
}

/**
 * Animates height via the CSS grid trick:
 * grid-template-rows transitions between 0fr and 1fr,
 * and the inner div clips overflow while collapsed.
 */
export default function Collapsible({ open, children }: Props) {
  return (
    <div
      className="grid transition-all duration-200 ease-in-out"
      style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
    >
      <div className="overflow-hidden">
        {children}
      </div>
    </div>
  );
}
