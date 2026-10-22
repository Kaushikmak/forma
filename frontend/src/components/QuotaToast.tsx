import { useEffect, useState } from "react";
import type { QuotaData } from "../hooks/useQuota";

interface QuotaToastProps {
  isOpen: boolean;
  onClose: () => void;
  quota?: QuotaData | null;
  clickCount: number;
  mediaType?: "image" | "video";
  onRefill?: () => void;
}

const WEIRD_MESSAGES: string[] = [
  "Quota limit reached. Please wait for refill",
  "Quota limit reached, just stfu I have free tier vps",
  "Stop spamming the button, the pixels can't move any faster",
  "How about you go touch some grass?",
  "Wait up, my poor ahh VPS can't handle your requests",
  "Bro, clicking again won't magically give you credits",
];

export default function QuotaToast({
  isOpen,
  onClose,
  quota,
  clickCount,
  onRefill,
}: QuotaToastProps) {
  const [visible, setVisible] = useState(false);

  // Smooth entrance and auto-close
  useEffect(() => {
    if (!isOpen) {
      const timer = setTimeout(() => {
        setVisible(false);
      }, 0);
      return () => clearTimeout(timer);
    }

    const enterTimer = setTimeout(() => {
      setVisible(true);
    }, 20);

    const autoCloseTimer = setTimeout(() => {
      setVisible(false);
      setTimeout(onClose, 300);
    }, 5000);

    return () => {
      clearTimeout(enterTimer);
      clearTimeout(autoCloseTimer);
    };
  }, [isOpen, clickCount, onClose]);

  if (!isOpen && !visible) {
    return null;
  }

  const messageIndex = Math.min(
    Math.max(0, clickCount - 1),
    WEIRD_MESSAGES.length - 1,
  );
  const message = WEIRD_MESSAGES[messageIndex];

  return (
    <aside
      role="status"
      aria-live="polite"
      className={[
        "fixed top-5 left-1/2 z-50",
        "w-[92vw] max-w-md",
        "-translate-x-1/2",
        "rounded-2xl border border-amber-500/30",
        "bg-zinc-950/95 backdrop-blur-xl",
        "p-4 sm:p-5",
        "shadow-2xl shadow-black/80",
        "transition-all duration-300 ease-out",
        visible
          ? "translate-y-0 opacity-100 scale-100"
          : "-translate-y-4 opacity-0 scale-95",
      ].join(" ")}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="mt-1 text-xs sm:text-sm leading-relaxed text-zinc-400">
            {message}
          </p>
        </div>
      </div>
    </aside>
  );
}
