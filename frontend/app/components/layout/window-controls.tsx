import { Copy, Minus, Square, X } from "lucide-react";
import { useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import {
  getWindowControls,
  getWindowMaximized,
  subscribeWindowMaximized,
} from "@/app/lib/desktop";

/** Self-drawn minimize/maximize/close buttons for the frameless Windows/Linux desktop window. */
export default function WindowControls() {
  const { t } = useTranslation();
  const controls = getWindowControls();
  const maximized = useSyncExternalStore(subscribeWindowMaximized, getWindowMaximized, () => false);
  if (!controls) return null;
  const maximizeLabel = t(maximized ? "window.restore" : "window.maximize");
  return (
    <div className="window-controls app-region-no-drag" role="group" aria-label={t("window.controls")}>
      <button type="button" className="window-control" aria-label={t("window.minimize")} title={t("window.minimize")} onClick={() => controls.minimize()}>
        <Minus size={16} strokeWidth={1.5} aria-hidden="true" />
      </button>
      <button type="button" className="window-control" aria-label={maximizeLabel} title={maximizeLabel} onClick={() => controls.toggleMaximize()}>
        {maximized
          ? <Copy size={13} strokeWidth={1.5} className="-scale-x-100" aria-hidden="true" />
          : <Square size={12} strokeWidth={1.5} aria-hidden="true" />}
      </button>
      <button type="button" className="window-control is-close" aria-label={t("window.close")} title={t("window.close")} onClick={() => controls.close()}>
        <X size={17} strokeWidth={1.4} aria-hidden="true" />
      </button>
    </div>
  );
}
