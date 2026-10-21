import { useState } from "react";
import type { LegoParams, LocalMediaFile } from "../types/types";

interface DownloadModalProps {
  isOpen: boolean;
  onClose: () => void;
  media: LocalMediaFile;
  params: LegoParams;
  resultUrl: string;
}

// 16 Megapixel max canvas limit (e.g. 4000x4000)
const MAX_EXPORT_PIXELS = 16_000_000;

export default function DownloadModal({
  isOpen,
  onClose,
  media,
  params,
  resultUrl,
}: DownloadModalProps) {
  const [scale, setScale] = useState<1 | 2 | 4>(1);
  const [format, setFormat] = useState<"png" | "jpeg">("png");
  const [downloading, setDownloading] = useState(false);

  if (!isOpen) return null;

  const isVideo = media.type === "video";
  const isGif = media.type === "gif";

  const gridHeight = Math.max(
    1,
    Math.round((params.width * media.height) / media.width),
  );
  const baseWidth = params.width * params.tileSize;
  const baseHeight = gridHeight * params.tileSize;

  const targetWidth = baseWidth * scale;
  const targetHeight = baseHeight * scale;
  const targetPixels = targetWidth * targetHeight;
  const isTooLarge = targetPixels > MAX_EXPORT_PIXELS;

  const handleDownload = async () => {
    setDownloading(true);
    try {
      if (isVideo || isGif || (scale === 1 && format === "png")) {
        const ext = isVideo ? "mp4" : isGif ? "gif" : "png";
        const filename = `forma-lego-${params.width}studs-${params.palette}.${ext}`;

        const res = await fetch(resultUrl);
        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(blobUrl);
      } else {
        const img = new Image();
        img.crossOrigin = "anonymous";
        await new Promise((resolve, reject) => {
          img.onload = resolve;
          img.onerror = () =>
            reject(new Error("Failed to load mosaic image for export"));
          img.src = resultUrl;
        });

        const canvas = document.createElement("canvas");
        canvas.width = targetWidth;
        canvas.height = targetHeight;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("Could not initialize 2D context");

        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(img, 0, 0, targetWidth, targetHeight);

        const mime = format === "jpeg" ? "image/jpeg" : "image/png";
        const quality = format === "jpeg" ? 0.95 : undefined;

        const blob = await new Promise<Blob | null>((resolve) =>
          canvas.toBlob(resolve, mime, quality),
        );

        if (!blob) throw new Error("Failed to export image blob");

        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = `forma-lego-${targetWidth}x${targetHeight}-${scale}x.${format === "jpeg" ? "jpg" : "png"}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(blobUrl);
      }
      onClose();
    } catch (err) {
      console.error("Export error:", err);
      alert(err instanceof Error ? err.message : "Failed to download mosaic.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-3 sm:p-4 animate-in fade-in duration-150">
      <div className="w-full max-w-md max-h-[90dvh] overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-900 p-4 sm:p-6 shadow-2xl flex flex-col gap-4 sm:gap-5 text-zinc-100">
        <div className="flex items-start justify-between border-b border-zinc-800 pb-3">
          <div>
            <h3 className="text-base font-semibold text-white tracking-tight">
              Export LEGO Mosaic
            </h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              {isVideo
                ? "H.264 MP4 Video"
                : isGif
                  ? "Animated GIF"
                  : "High-Resolution Image"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-400 hover:text-white p-2 sm:p-1 rounded-lg hover:bg-zinc-800 transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center"
          >
            ✕
          </button>
        </div>

        <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/60 p-3.5 space-y-1.5 text-xs font-mono">
          <div className="flex justify-between text-zinc-400">
            <span>Grid Width:</span>
            <span className="text-zinc-200">{params.width} studs</span>
          </div>
          <div className="flex justify-between text-zinc-400">
            <span>Grid Height:</span>
            <span className="text-zinc-200">{gridHeight} studs</span>
          </div>
          <div className="flex justify-between text-zinc-400">
            <span>Palette:</span>
            <span className="text-zinc-200 capitalize">{params.palette}</span>
          </div>
          <div className="flex justify-between text-zinc-400">
            <span>Base Resolution:</span>
            <span className="text-zinc-200">
              {baseWidth} x {baseHeight} px
            </span>
          </div>
        </div>

        {!isVideo && !isGif && (
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-xs font-medium text-zinc-300">
                Resolution Scale
              </label>
              <div className="grid grid-cols-3 gap-2">
                {([1, 2, 4] as const).map((s) => {
                  const w = baseWidth * s;
                  const h = baseHeight * s;
                  const tooBig = w * h > MAX_EXPORT_PIXELS;
                  return (
                    <button
                      key={s}
                      type="button"
                      disabled={tooBig}
                      onClick={() => setScale(s)}
                      className={[
                        "flex flex-col items-center justify-center p-2 sm:p-2.5 min-h-[52px] rounded-xl border text-center transition-all",
                        tooBig
                          ? "opacity-30 border-zinc-800 bg-zinc-950 cursor-not-allowed"
                          : scale === s
                            ? "border-white bg-white text-black font-semibold shadow-md"
                            : "border-zinc-800 bg-zinc-950/70 text-zinc-300 hover:bg-zinc-800 hover:text-white",
                      ].join(" ")}
                    >
                      <span className="text-sm font-bold font-mono">{s}x</span>
                      <span className="text-[10px] mt-0.5 opacity-80 font-mono">
                        {w}x{h}
                      </span>
                    </button>
                  );
                })}
              </div>
              {isTooLarge && (
                <p className="text-[11px] text-amber-400 font-medium">
                  Selected scale exceeds the 16 MP safety limit.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium text-zinc-300">
                File Format
              </label>
              <div className="grid grid-cols-2 gap-2">
                {(["png", "jpeg"] as const).map((fmt) => (
                  <button
                    key={fmt}
                    type="button"
                    onClick={() => setFormat(fmt)}
                    className={[
                      "py-2.5 sm:py-2 px-3 min-h-[40px] rounded-xl border text-xs font-medium uppercase font-mono transition-all flex items-center justify-center",
                      format === fmt
                        ? "border-white bg-white text-black font-semibold"
                        : "border-zinc-800 bg-zinc-950/70 text-zinc-300 hover:bg-zinc-800 hover:text-white",
                    ].join(" ")}
                  >
                    {fmt === "jpeg" ? "JPEG (95%)" : "PNG (Lossless)"}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-end gap-2.5 pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={downloading}
            className="px-4 py-2.5 sm:py-2 min-h-[40px] rounded-xl border border-zinc-700 bg-zinc-800/80 text-xs font-medium text-zinc-300 hover:bg-zinc-700 hover:text-white transition-colors flex items-center justify-center"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDownload}
            disabled={downloading || isTooLarge}
            className={[
              "px-5 py-2.5 sm:py-2 min-h-[40px] rounded-xl text-xs font-semibold tracking-wide transition-all flex items-center justify-center",
              downloading || isTooLarge
                ? "bg-zinc-800 text-zinc-500 cursor-not-allowed opacity-50"
                : "bg-white text-black hover:bg-zinc-200 active:scale-[0.98] shadow-lg shadow-white/5",
            ].join(" ")}
          >
            {downloading ? "Preparing..." : "Download Now"}
          </button>
        </div>
      </div>
    </div>
  );
}
