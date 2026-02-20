interface Props {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}

export default function InfoModal({ title, onClose, children }: Props) {
  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="card-d2 w-full max-w-lg animate-fadeIn"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-3 border-b border-d2bg-border flex items-center justify-between">
          <h2 className="font-diablo text-d2gold tracking-widest text-sm">{title}</h2>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-200 text-xl leading-none transition-colors w-6 h-6 flex items-center justify-center"
          >
            ×
          </button>
        </div>
        <div className="p-5 max-h-[70vh] overflow-y-auto text-sm text-slate-400 leading-relaxed space-y-3">
          {children}
        </div>
      </div>
    </div>
  );
}
