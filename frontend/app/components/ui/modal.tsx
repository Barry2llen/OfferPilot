import { AnimatePresence, motion } from "motion/react";
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import WindowControls from "@/app/components/layout/window-controls";

function trapFocus(event: KeyboardEvent<HTMLDialogElement>) {
  const dialog = event.currentTarget;
  if (event.key !== "Tab" || (event.target as Element).closest("dialog") !== dialog) return;
  const controls = Array.from(dialog.querySelectorAll<HTMLElement>(
    'button, input, select, textarea, a[href], [tabindex]',
  )).filter((element) => element.tabIndex >= 0 && !element.matches(":disabled") && element.getClientRects().length > 0);
  const first = controls[0];
  const last = controls.at(-1);
  if (!first) {
    event.preventDefault();
    dialog.focus();
  } else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

/** Native dialog provides focus containment, inert background, Escape and focus restoration. */
export interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  drawer?: boolean;
  busy?: boolean;
  /** Fixed area under the heading, e.g. a search field that should not scroll away. */
  toolbar?: ReactNode;
  /** Fixed action bar pinned to the bottom of the surface. */
  footer?: ReactNode;
}

export default function Modal({ open, title, onClose, children, drawer = false, busy = false, toolbar, footer }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const { t } = useTranslation();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open) {
      dialog.showModal();
      dialog.dataset.closing = "false";
    } else if (dialog.open) {
      dialog.dataset.closing = "true";
      const timer = window.setTimeout(() => dialog.close(), matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 220);
      return () => clearTimeout(timer);
    }
  }, [open]);
  return createPortal(
    <dialog ref={ref} tabIndex={-1} onKeyDown={trapFocus} aria-labelledby={titleId} className={`op-modal ${drawer ? "op-drawer" : ""}`}
      onCancel={(e) => { e.preventDefault(); e.stopPropagation(); if (!busy) onClose(); }}
      onClick={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className="modal-surface">
        <header className="modal-heading"><h2 id={titleId}>{title}</h2>
          <button type="button" className="icon-button" disabled={busy} aria-label={t("common.close")} onClick={onClose}><X size={20} /></button>
        </header>
        {toolbar && <div className="modal-toolbar">{toolbar}</div>}
        <div className="modal-content"><AnimatePresence initial={false}>{open && <motion.div key="content" exit={{ opacity: 0 }} transition={{ duration: 0.22 }}>{children}</motion.div>}</AnimatePresence></div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </div>
      {/* The modal sits in the top layer, so the window buttons are repeated here to stay reachable. */}
      <WindowControls />
    </dialog>, document.body);
}
