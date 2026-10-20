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
  const [remainingSec, setRemainingSec] = useState<number>(0);

  // Live countdown timer inside effect (pure render)
  useEffect(() => {
    if (!isOpen) return;

    const baseResetAt = quota?.resetAt
      ? quota.resetAt
      : quota?.resetsInSeconds
      ? Date.now() + quota.resetsInSeconds * 1000
      : Date.now() + 1800000;

    const updateTimer = () => {
      const now = Date.now();
      const diff = Math.max(0, Math.ceil((baseResetAt - now) / 1000));
      setRemainingSec(diff);
      if (diff <= 0 && onRefill) {
        onRefill();
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [isOpen, quota, onRefill]);

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
    }, 8000);

    return () => {
      clearTimeout(enterTimer);
      clearTimeout(autoCloseTimer);
    };
  }, [isOpen, clickCount, onClose]);

  if (!isOpen && !visible) {
    return null;
  }

  // Format countdown string: MM:SS
  const formatCountdown = (totalSeconds: number) => {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    if (mins > 0) {
      return `${mins}m ${secs.toString().padStart(2, "0")}s`;
    }
    return `${secs}s`;
  };

  const messageIndex = Math.min(
    Math.max(0, clickCount - 1),
    WEIRD_MESSAGES.length - 1
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
        visible ? "translate-y-0 opacity-100 scale-100" : "-translate-y-4 opacity-0 scale-95",
      ].join(" ")}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20 text-lg">
          ⏳
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-zinc-100">
              Refill Countdown
            </h4>
            <span className="inline-flex items-center rounded-md bg-amber-500/10 px-2 py-0.5 text-xs font-mono font-medium text-amber-400 border border-amber-500/20">
              {formatCountdown(remainingSec)}
            </span>
          </div>
          <p className="mt-1 text-xs sm:text-sm leading-relaxed text-zinc-400">
            {message}
          </p>
          {clickCount > 1 && (
            <p className="mt-2 text-[11px] font-mono text-zinc-500">
              Attempt {Math.min(clickCount, 10)} / 10
            </p>
          )}
        </div>
      </div>
    </aside>
  );
}
