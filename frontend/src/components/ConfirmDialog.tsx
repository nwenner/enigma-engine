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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-d2bg-surface border border-d2bg-border rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl">
        <h2 className="text-d2gold font-bold text-lg mb-2">{title}</h2>
        <p className="text-amber-200 text-sm mb-6">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded border border-d2bg-border text-amber-300 hover:bg-d2bg-elevated transition-colors text-sm"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              danger
                ? "bg-red-800 hover:bg-red-700 text-red-100 border border-red-700"
                : "bg-d2gold hover:bg-d2gold-light text-d2bg font-bold"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
