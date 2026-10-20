import React, { useRef, useState } from "react";
import type { LocalMediaFile } from "../types/types";
import { useMediaInspector } from "../hooks/useMediaInspector";

interface MediaDropBoxProps {
  onMediaSelect: (media: LocalMediaFile) => void;
  disabled?: boolean;
}

export default function MediaDropBox({
  onMediaSelect,
  disabled = false,
}: MediaDropBoxProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const { inspect, loading, error } = useMediaInspector();

  const processFile = async (file: File) => {
    if (disabled || loading) {
      return;
    }
    const media = await inspect(file);
    if (media) {
      onMediaSelect(media);
    }
  };

  const handleFileInput = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      processFile(file);
    }
    event.target.value = "";
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (disabled) return;
    setIsDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) {
      processFile(file);
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!disabled) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleClick = () => {
    if (!disabled && !loading) {
      inputRef.current?.click();
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleClick();
    }
  };

  return (
    <div className="w-full">
      <div
        className={[
          "min-h-64 sm:min-h-80 w-full rounded-2xl border border-dashed transition-all duration-200",
          "flex flex-col items-center justify-center cursor-pointer p-5 sm:p-8 select-none",
          isDragging
            ? "border-white bg-zinc-800/50 scale-[0.99]"
            : "border-zinc-700/80 bg-zinc-900/30 hover:border-zinc-500 hover:bg-zinc-900/50",
          disabled && "cursor-not-allowed opacity-50",
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={handleClick}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={disabled ? -1 : 0}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp,.gif,.bmp,.tiff,.mp4,.webm,.mov,.avi"
          onChange={handleFileInput}
          hidden
          disabled={disabled}
        />

        {loading ? (
          <div className="flex flex-col items-center gap-3">
            <div className="w-6 h-6 border-2 border-zinc-500 border-t-white rounded-full animate-spin" />
            <p className="text-sm text-zinc-400 font-medium">
              Inspecting media &amp; dimensions...
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center text-center max-w-sm">
            <div className="w-12 h-12 rounded-xl bg-zinc-800/80 border border-zinc-700/60 flex items-center justify-center mb-4 text-zinc-300">
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>

            <h3 className="text-base font-semibold text-zinc-100 mb-1">
              Drag n' Drop your media
            </h3>

            <p className="text-xs text-zinc-400 mb-5">
              or{" "}
              <span className="text-white underline underline-offset-2 hover:text-zinc-200">
                browse from computer
              </span>
            </p>

            <div className="flex flex-wrap items-center justify-center gap-1.5 text-[11px] text-zinc-500">
              <span className="px-2 py-2 rounded-full bg-zinc-800/60 border border-zinc-700/50">
                Images, GIFs and Videos: PNG, JPG, WebP
              </span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-3 px-3 py-2 rounded-xl bg-red-950/40 border border-red-900/60 text-xs text-red-300">
          {error}
        </div>
      )}
    </div>
  );
}
