import type {
  JobState,
  LegoFps,
  LegoParams,
  LegoQuality,
  LocalMediaFile,
} from "../types/types";
import type { QuotaData } from "../hooks/useQuota";

interface ControlsSidebarProps {
  media: LocalMediaFile | null;
  params: LegoParams;
  onParamsChange: (params: LegoParams) => void;
  disabled?: boolean;
  job?: JobState;
  isRendering?: boolean;
  quota?: QuotaData | null;
  onCreateMosaic?: () => void;
  onOpenDownload?: () => void;
  onQuotaExceeded?: () => void;
}

const WIDTH_PRESETS = [32, 48, 64, 96, 128];
const TILE_SIZES = [8, 12, 16, 24, 32];
const QUALITIES: { id: LegoQuality; label: string; desc: string }[] = [
  { id: "standard", label: "Std", desc: "Fast (5-bit LUT)" },
  { id: "high", label: "High", desc: "Balanced (6-bit LUT)" },
  { id: "maximum", label: "Max", desc: "Exact CIELAB" },
];

export default function ControlsSidebar({
  media,
  params,
  onParamsChange,
  disabled = false,
  job,
  isRendering = false,
  quota,
  onCreateMosaic,
  onOpenDownload,
  onQuotaExceeded,
}: ControlsSidebarProps) {
  const isBusy =
    Boolean(isRendering) ||
    job?.status === "validating" ||
    job?.status === "uploading" ||
    job?.status === "queued" ||
    job?.status === "probing" ||
    job?.status === "processing" ||
    job?.status === "encoding";

  const isDone = job?.status === "done" && Boolean(job?.resultUrl);
  const isVideo = media?.type === "video";
  const isVideoOrGif = media?.type === "video" || media?.type === "gif";
  const remainingQuota = quota
    ? isVideo
      ? quota.videos.remaining
      : quota.images.remaining
    : undefined;
  const isQuotaExhausted = remainingQuota !== undefined && remainingQuota <= 0;
  const canCreate = Boolean(media) && !isBusy && !disabled && !isQuotaExhausted;

  // Calculate output dimensions
  const sourceWidth = media?.width ?? 1920;
  const sourceHeight = media?.height ?? 1080;
  const gridHeight = Math.max(
    1,
    Math.round((params.width * sourceHeight) / sourceWidth),
  );
  const outputWidth = params.width * params.tileSize;
  const outputHeight = gridHeight * params.tileSize;
  const totalStuds = params.width * gridHeight;

  const updateParam = <K extends keyof LegoParams>(
    key: K,
    value: LegoParams[K],
  ) => {
    if (isQuotaExhausted) {
      onQuotaExceeded?.();
      return;
    }
    onParamsChange({
      ...params,
      [key]: value,
    });
  };

  return (
    <aside className="w-full rounded-2xl border border-zinc-800/80 bg-zinc-900/60 p-4 sm:p-5 backdrop-blur-md text-zinc-100 flex flex-col gap-5 sm:gap-6">
      <div className="pt-2 space-y-2.5">
        {isDone && onOpenDownload ? (
          <div className="space-y-2">
            <button
              type="button"
              onClick={onOpenDownload}
              className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl font-bold text-xs tracking-wider bg-emerald-600 hover:bg-emerald-500 text-blackshadow-emerald-500/20 transition-all active:scale-[0.98] cursor-pointer"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth="2.5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
              <span>Download</span>
            </button>

            {onCreateMosaic && (
              <button
                type="button"
                onClick={() => {
                  if (isQuotaExhausted) {
                    onQuotaExceeded?.();
                    return;
                  }
                  onCreateMosaic();
                }}
                disabled={isBusy}
                className={[
                  "w-full py-2 px-3 rounded-lg text-xs font-medium transition-all border text-center",
                  isBusy
                    ? "opacity-40 cursor-not-allowed text-zinc-500 bg-zinc-900 border-zinc-800"
                    : isQuotaExhausted
                      ? "text-red-400 hover:text-red-300 bg-red-950/30 hover:bg-red-950/50 border-red-900/60 cursor-pointer"
                      : "text-zinc-400 hover:text-white bg-zinc-800/40 hover:bg-zinc-800 border-zinc-800 cursor-pointer",
                ].join(" ")}
              >
                {isBusy ? "Rendering..." : "Render media"}
              </button>
            )}
          </div>
        ) : (
          <button
            type="button"
            onClick={() => {
              if (isQuotaExhausted) {
                onQuotaExceeded?.();
                return;
              }
              onCreateMosaic?.();
            }}
            disabled={(!canCreate && !isQuotaExhausted) || !onCreateMosaic}
            className={[
              "w-full py-3.5 px-4 rounded-xl font-bold text-xs tracking-wider transition-all flex items-center justify-center gap-2.5",
              isQuotaExhausted
                ? "bg-red-950/70 text-red-300 hover:bg-red-900/80 active:scale-[0.98] border border-red-800/80 cursor-pointer shadow-lg shadow-red-950/30"
                : canCreate && onCreateMosaic
                  ? "bg-white text-black hover:bg-zinc-200 active:scale-[0.98] shadow-lg shadow-white/10 cursor-pointer"
                  : "bg-zinc-800/70 text-zinc-500 cursor-not-allowed border border-zinc-800/80 opacity-60",
            ].join(" ")}
          >
            {isBusy ? (
              <>
                <span className="inline-block w-3.5 h-3.5 border-2 border-zinc-400   rounded-full animate-spin shrink-0" />
                <span>Rendering...</span>
              </>
            ) : isQuotaExhausted ? (
              <span>
                Limit reached (
                {Math.max(1, Math.ceil((quota?.resetsInSeconds ?? 0) / 60))}m
                reset)
              </span>
            ) : media ? (
              <>
                <span>Render</span>
              </>
            ) : (
              <>
                <span>Upload to create</span>
              </>
            )}
          </button>
        )}
      </div>

      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <label
            htmlFor="mosaic-width"
            className="text-xs font-medium text-zinc-300"
          >
            Grid Width
          </label>
          <div className="flex items-baseline gap-1">
            <span className="text-sm font-semibold font-mono text-white">
              {params.width}
            </span>
            <span className="text-[11px] text-zinc-500">studs</span>
          </div>
        </div>

        <input
          id="mosaic-width"
          type="range"
          min={16}
          max={256}
          step={1}
          value={params.width}
          onChange={(e) => updateParam("width", Number(e.target.value))}
          disabled={disabled}
          className="w-full"
        />

        <div className="flex min-w-0 items-center gap-1.5 overflow-x-auto pt-0.5">
          <span className="shrink-0 text-[10px] text-zinc-500 uppercase tracking-wider mr-1">
            Presets:
          </span>

          {WIDTH_PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => updateParam("width", preset)}
              disabled={disabled}
              className={[
                "shrink-0 px-2.5 py-1 sm:py-0.5 text-xs rounded-md font-mono transition-all",
                params.width === preset
                  ? "bg-white text-black font-medium"
                  : "bg-zinc-800/80 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800",
              ].join(" ")}
            >
              {preset}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-zinc-300">
            Tile Scale
          </label>
        </div>

        <div className="grid grid-cols-5 gap-1.5 p-1 rounded-xl bg-zinc-950/60 border border-zinc-800">
          {TILE_SIZES.map((size) => (
            <button
              key={size}
              type="button"
              onClick={() => updateParam("tileSize", size)}
              disabled={disabled}
              className={[
                "py-2 sm:py-1.5 min-h-[36px] text-xs rounded-lg font-mono font-medium transition-all text-center flex items-center justify-center",
                params.tileSize === size
                  ? "bg-white text-black shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50",
              ].join(" ")}
            >
              {size}px
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2.5">
        <label className="text-xs font-medium text-zinc-300 block">
          Color Palette
          <p className="text-[10px] text-gray-300">
            have more ideas?{" "}
            <a
              className="underline"
              target="_blank"
              href="https://github.com/Kaushikmak/forma"
            >
              make a pr
            </a>
          </p>
        </label>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => updateParam("palette", "classic")}
            disabled={disabled}
            className={[
              "p-2.5 sm:p-3 rounded-xl border text-left transition-all relative flex flex-col justify-between min-h-[76px] sm:h-20",
              params.palette === "classic"
                ? "border-white bg-zinc-800/70 shadow-sm"
                : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700",
            ].join(" ")}
          >
            <div className="text-xs font-medium text-white">Classic</div>

            <div className="flex gap-1">
              <span className="w-2.5 h-2.5 rounded-full bg-[#c91a09]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#f2cd37]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#0055bf]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#237841]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#ffffff]" />
            </div>
          </button>

          <button
            type="button"
            onClick={() => updateParam("palette", "extended")}
            disabled={disabled}
            className={[
              "p-2.5 sm:p-3 rounded-xl border text-left transition-all relative flex flex-col justify-between min-h-[76px] sm:h-20",
              params.palette === "extended"
                ? "border-white bg-zinc-800/70 shadow-sm"
                : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700",
            ].join(" ")}
          >
            <div className="text-xs font-medium text-white">Extended</div>

            <div className="flex gap-1">
              <span className="w-2.5 h-2.5 rounded-full bg-[#898788]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#ba9842]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#9bb0d9]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#a06eb9]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#e6e3da]" />
            </div>
          </button>
        </div>
      </div>

      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-zinc-300">Quality</label>
        </div>

        <div className="grid grid-cols-3 gap-1.5 p-1 rounded-xl bg-zinc-950/60 border border-zinc-800">
          {QUALITIES.map((q) => (
            <button
              key={q.id}
              type="button"
              onClick={() => updateParam("quality", q.id)}
              disabled={disabled}
              className={[
                "py-2 sm:py-1.5 min-h-[36px] text-xs rounded-lg font-medium transition-all text-center flex items-center justify-center",
                params.quality === q.id
                  ? "bg-white text-black shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50",
              ].join(" ")}
            >
              {q.label}
            </button>
          ))}
        </div>
      </div>

      {isVideoOrGif && (
        <div className="space-y-2.5 pt-1   border-zinc-800/60">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-zinc-300">
              Output Frame Rate
            </label>
            {media?.type === "gif" && (
              <span className="text-[10px] text-zinc-500">GIF max 30 FPS</span>
            )}
          </div>

          <div className="grid grid-cols-4 gap-1 p-1 rounded-xl bg-zinc-950/60 border border-zinc-800">
            {(["original", "24", "30", "60"] as LegoFps[]).map((f) => {
              const isBlocked = media?.type === "gif" && f === "60";
              return (
                <button
                  key={f}
                  type="button"
                  onClick={() => !isBlocked && updateParam("fps", f)}
                  disabled={disabled || isBlocked}
                  title={isBlocked ? "60 FPS not supported for GIF" : undefined}
                  className={[
                    "py-2 sm:py-1.5 min-h-[36px] text-xs rounded-lg font-mono transition-all text-center flex items-center justify-center",
                    params.fps === f && !isBlocked
                      ? "bg-white text-black font-medium shadow-sm"
                      : isBlocked
                        ? "opacity-30 cursor-not-allowed text-zinc-600 line-through"
                        : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50",
                  ].join(" ")}
                >
                  {f === "original" ? "Orig" : `${f}fps`}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {media?.type === "video" && (
        <div className="space-y-2.5 pt-1   border-zinc-800/60">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-zinc-300">
              Video Bitrate
            </label>
            <div className="flex gap-1 bg-zinc-950/80 p-0.5 rounded-lg border border-zinc-800 text-[10px]">
              <button
                type="button"
                onClick={() => updateParam("autoBitrate", true)}
                className={[
                  "px-2 py-0.5 rounded transition-all",
                  params.autoBitrate
                    ? "bg-zinc-700 text-white font-medium"
                    : "text-zinc-400",
                ].join(" ")}
              >
                Auto (50MB Cap)
              </button>
              <button
                type="button"
                onClick={() => {
                  updateParam("autoBitrate", false);
                  if (!params.bitrateMbps) updateParam("bitrateMbps", 4.0);
                }}
                className={[
                  "px-2 py-0.5 rounded transition-all",
                  !params.autoBitrate
                    ? "bg-zinc-700 text-white font-medium"
                    : "text-zinc-400",
                ].join(" ")}
              >
                Custom
              </button>
            </div>
          </div>

          {!params.autoBitrate && (
            <div className="space-y-1.5 pt-1">
              <div className="flex justify-between text-xs text-zinc-400 font-mono">
                <span>Target Bitrate</span>
                <span>{(params.bitrateMbps ?? 4.0).toFixed(1)} Mbps</span>
              </div>
              <input
                type="range"
                min={0.5}
                max={20.0}
                step={0.5}
                value={params.bitrateMbps ?? 4.0}
                onChange={(e) =>
                  updateParam("bitrateMbps", Number(e.target.value))
                }
                disabled={disabled}
                className="w-full"
              />
            </div>
          )}
        </div>
      )}
      {media ? (
        <div className="rounded-xl bg-zinc-950/80 border border-zinc-800/90 p-3.5 space-y-2 text-xs">
          <div className="flex justify-between text-zinc-400">
            <span>Resolution</span>
            <span className="font-mono text-zinc-200">
              {outputWidth} × {outputHeight} px
            </span>
          </div>
          <div className="flex justify-between text-zinc-400">
            <span>Grid Studs</span>
            <span className="font-mono text-zinc-200">
              {params.width} × {gridHeight} ({totalStuds.toLocaleString()})
            </span>
          </div>
          <div className="flex justify-between items-center text-zinc-400   border-zinc-800/60 pt-2">
            <span>Quota</span>
            <span
              className={`font-mono font-medium ${
                isQuotaExhausted ? "text-red-400 font-bold" : "text-emerald-400"
              }`}
            >
              {isVideo
                ? `${quota?.videos.remaining ?? 10}/${quota?.videos.limit ?? 10} videos left`
                : `${quota?.images.remaining ?? 30}/${quota?.images.limit ?? 30} images left`}
            </span>
          </div>
        </div>
      ) : (
        <></>
      )}
    </aside>
  );
}
