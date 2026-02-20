interface Props {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
}

export default function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  danger = false,
}: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm animate-fadeIn">
      <div className="card-d2 p-6 max-w-md w-full mx-4 shadow-2xl shadow-black/60">
        <h2 className="font-diablo text-d2gold text-base tracking-wide mb-3">{title}</h2>
        <p className="text-slate-300 text-sm leading-relaxed mb-6">{message}</p>
        <div className="flex justify-end gap-3">
          <button onClick={onCancel} className="btn-d2-ghost">
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={danger ? "btn-d2-danger" : "btn-d2"}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
