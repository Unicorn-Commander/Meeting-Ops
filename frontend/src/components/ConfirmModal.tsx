import { useEffect } from 'react';
import { AlertTriangle, X } from 'lucide-react';

/**
 * Generic confirm dialog matched to the existing modal styling
 * (EmailAttendeesModal / SessionPermissionsModal). Used in place of
 * `window.confirm()` for the simultaneous-recording guard so we get a
 * non-blocking, theme-consistent prompt.
 *
 * Renders nothing when `isOpen` is false.
 */

export interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  /** Body content — string or any ReactNode. Long-form ok. */
  description: React.ReactNode;
  /** "Yes, do it" button label. Defaults to 'Confirm'. */
  confirmLabel?: string;
  /** "Don't do it" button label. Defaults to 'Cancel'. */
  cancelLabel?: string;
  /**
   * Visual tone for the primary action button. 'danger' = red, 'primary'
   * = the brand fuchsia/indigo. Defaults to 'danger' since the most
   * common use is "stop other recording".
   */
  tone?: 'danger' | 'primary';
  onConfirm: () => void;
  onCancel: () => void;
  /**
   * Optional icon override. Defaults to AlertTriangle for danger tone
   * and undefined for primary.
   */
  icon?: React.ReactNode;
}

export default function ConfirmModal({
  isOpen,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  onConfirm,
  onCancel,
  icon,
}: ConfirmModalProps) {
  // Escape-to-cancel — same convention as the rest of the app's modals.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  const showIcon = icon ?? (tone === 'danger' ? (
    <AlertTriangle className="h-5 w-5 text-amber-300" />
  ) : null);

  const confirmClasses = tone === 'danger'
    ? 'bg-red-600 hover:bg-red-500 text-white'
    : 'bg-gradient-to-r from-fuchsia-600 to-indigo-600 hover:from-fuchsia-500 hover:to-indigo-500 text-white';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      onClick={(event) => {
        // Click-outside-to-cancel. The inner container stops propagation
        // so clicking the modal body doesn't trigger this.
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 shadow-2xl shadow-black/60">
        <div className="flex items-start justify-between gap-3 border-b border-zinc-800 px-5 py-4">
          <div className="flex items-start gap-3">
            {showIcon}
            <h2 id="confirm-modal-title" className="text-base font-semibold text-white">
              {title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md p-1 text-zinc-400 transition hover:bg-zinc-800 hover:text-zinc-200"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-4 text-sm leading-6 text-zinc-200">
          {description}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-zinc-800 px-5 py-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-zinc-700"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${confirmClasses}`}
            autoFocus
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
