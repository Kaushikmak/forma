import { useEffect, useRef, useState, type CSSProperties } from "react";
import type {
  AsciiPalette,
  JobState,
  LegoFps,
  LegoPalette,
  LegoParams,
  LegoQuality,
  LocalMediaFile,
  StyleId,
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

const LEGO_PALETTES: {
  id: LegoPalette;
  name: string;
  colors: string[];
}[] = [
  {
    id: "classic",
    name: "Classic",
    colors: ["#c91a09", "#f2cd37", "#0055bf", "#237841", "#ffffff"],
  },
  {
    id: "extended",
    name: "Extended",
    colors: ["#898788", "#ba9842", "#9bb0d9", "#a06eb9", "#e6e3da"],
  },
  {
    id: "monochrome",
    name: "Monochrome",
    colors: ["#ffffff", "#e6e3e0", "#a0a5a9", "#6c6e68", "#05131d"],
  },
  {
    id: "pastel",
    name: "Pastel",
    colors: ["#f2705e", "#ff698f", "#fbe696", "#b2d7b8", "#a06eb9"],
  },
  {
    id: "crayon",
    name: "Crayon",
    colors: ["#c91a09", "#fe8a18", "#f2cd37", "#237841", "#0055bf"],
  },
  {
    id: "earth",
    name: "Earth",
    colors: ["#582a12", "#7c503a", "#e4cd9e", "#aa7d55", "#184632"],
  },
  {
    id: "cool",
    name: "Cool",
    colors: ["#237841", "#0055bf", "#008f9b", "#81007b", "#a06eb9"],
  },
  {
    id: "warm",
    name: "Warm",
    colors: ["#c91a09", "#fe8a18", "#f2cd37", "#f785b1", "#cc702a"],
  },
];

const ASCII_PALETTES: {
  id: AsciiPalette;
  name: string;
  colors: string[];
}[] = [
  {
    id: "mild",
    name: "Mild Paper",
    colors: ["#faf7f1", "#e8dfd3", "#6e5d4e", "#3a3028"],
  },
  {
    id: "vibrant",
    name: "Vibrant",
    colors: ["#ffffff", "#ff4444", "#ffcc00", "#0088ff", "#00cc66"],
  },
  {
    id: "dark",
    name: "Dark Mode",
    colors: ["#14161c", "#282c37", "#8ba4d0", "#ffffff"],
  },
  {
    id: "matrix",
    name: "Matrix",
    colors: ["#0a100c", "#0f2618", "#19ff55", "#a3ffbe"],
  },
  {
    id: "amber",
    name: "Amber CRT",
    colors: ["#140e08", "#2a1c0d", "#ffb000", "#ffe082"],
  },
  {
    id: "cyberpunk",
    name: "Cyberpunk",
    colors: ["#100c1c", "#ff1493", "#00f0ff", "#bf55ec"],
  },
  {
    id: "monochrome",
    name: "Monochrome",
    colors: ["#ffffff", "#cccccc", "#666666", "#000000"],
  },
  {
    id: "retro",
    name: "Retro Sepia",
    colors: ["#f4ebd7", "#e2caa5", "#8c6239", "#402613"],
  },
  {
    id: "pastel",
    name: "Pastel",
    colors: ["#fcfaf8", "#ffd1dc", "#c1e1c1", "#c5d0e6"],
  },
  {
    id: "nord",
    name: "Nord Frost",
    colors: ["#2e3440", "#4c566a", "#88c0d0", "#eceff4"],
  },
  {
    id: "gameboy",
    name: "Game Boy",
    colors: ["#0f380f", "#306230", "#8bac0f", "#9bbc0f"],
  },
];

const ASCII_RAMPS: { id: string; name: string; sample: string }[] = [
  { id: "default", name: "Default", sample: "@#%&8*+=~-:. " },
  { id: "classic", name: "Classic", sample: "@%#*+=-:. " },
  { id: "dense", name: "Dense", sample: "$@B%8&WM#*... " },
  { id: "blocks", name: "Blocks", sample: "█▓▒░ " },
  { id: "simple", name: "Simple", sample: "#*+:. " },
];

type Bit = {
  id: number;
  left: number;
  delay: number;
  rot: number;
  color: string;
  char: string;
};

const LEGO_BIT_COLORS = ["#c91a09", "#f2cd37", "#0055bf", "#237841"];
const ASCII_BIT_COLORS = ["#10b981", "#ec4899", "#0ea5e9", "#f59e0b"];
const ASCII_BIT_CHARS = ["@", "#", "%", "&", "*", "+", "=", "~", "8"];

function makeBits(style: StyleId): Bit[] {
  const colors = style === "lego" ? LEGO_BIT_COLORS : ASCII_BIT_COLORS;
  const pick = <T,>(arr: T[]) => arr[Math.floor(Math.random() * arr.length)];
  return Array.from({ length: 12 }, (_, i) => ({
    id: i,
    left: 4 + Math.random() * 88, // % across the button
    delay: Math.random() * 0.25, // s
    rot: Math.round((Math.random() - 0.5) * 360),
    color: pick(colors),
    char: pick(ASCII_BIT_CHARS),
  }));
}

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
  const isAscii = params.style === "ascii";

  const [isPaletteOpen, setIsPaletteOpen] = useState(false);
  const paletteContainerRef = useRef<HTMLDivElement>(null);

  const [burst, setBurst] = useState<{
    style: StyleId;
    key: number;
    bits: Bit[];
  } | null>(null);
  const burstTimer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (burstTimer.current) window.clearTimeout(burstTimer.current);
    },
    [],
  );

  const triggerBurst = (style: StyleId) => {
    if (burstTimer.current) window.clearTimeout(burstTimer.current);
    setBurst({ style, key: Date.now(), bits: makeBits(style) });
    burstTimer.current = window.setTimeout(() => setBurst(null), 1050);
  };

  const renderBurst = (style: StyleId) => {
    if (burst?.style !== style) return null;
    return (
      <span
        key={burst.key}
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden motion-reduce:hidden"
      >
        {burst.bits.map((b) => {
          const anim: CSSProperties = {
            top: -12,
            left: `${b.left}%`,
            animation: "fall-bit 0.75s ease-in both",
            animationDelay: `${b.delay}s`,
            ["--rot" as string]: `${b.rot}deg`,
          };
          return style === "lego" ? (
            <span
              key={b.id}
              className="absolute block w-2.5 h-2 rounded-[2px]"
              style={{ ...anim, background: b.color }}
            >
              <span
                className="absolute -top-[2px] left-[3px] w-1 h-[2px] rounded-t-[1px]"
                style={{ background: b.color }}
              />
            </span>
          ) : (
            <span
              key={b.id}
              className="absolute font-mono font-bold text-[11px] leading-none"
              style={{ ...anim, color: b.color }}
            >
              {b.char}
            </span>
          );
        })}
      </span>
    );
  };

  useEffect(() => {
    function handleClickOutside(e: MouseEvent | TouchEvent) {
      if (
        paletteContainerRef.current &&
        !paletteContainerRef.current.contains(e.target as Node)
      ) {
        setIsPaletteOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isPaletteOpen) {
        setIsPaletteOpen(false);
      }
    }
    if (isPaletteOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("touchstart", handleClickOutside);
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isPaletteOpen]);

  const availablePalettes = isAscii ? ASCII_PALETTES : LEGO_PALETTES;
  const activePaletteObj =
    availablePalettes.find((p) => p.id === params.palette) ||
    availablePalettes[0];

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
  const totalUnits = params.width * gridHeight;

  // Recommended web bitrate for video
  const sourceBitrateMbps =
    isVideo && media?.sizeBytes && media?.durationSec && media.durationSec > 0
      ? (media.sizeBytes * 8) / (media.durationSec * 1_000_000)
      : undefined;

  const autoBitrateRecommendedMbps = sourceBitrateMbps
    ? Math.min(
        Math.max(Number((sourceBitrateMbps * 1.15).toFixed(1)), 1.5),
        4.0,
      )
    : 3.0;

  const isUpscaled = isVideo && outputWidth > sourceWidth * 1.15;
  const fittedTileSize = (() => {
    const candidates = [...TILE_SIZES].sort((a, b) => {
      const diffA = Math.abs(params.width * a - sourceWidth);
      const diffB = Math.abs(params.width * b - sourceWidth);
      return diffA - diffB;
    });
    return candidates[0] || 16;
  })();

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

  const handleStyleChange = (newStyle: StyleId) => {
    triggerBurst(newStyle);
    if (newStyle === params.style) return;
    setIsPaletteOpen(false);
    if (newStyle === "ascii") {
      onParamsChange({
        ...params,
        style: "ascii",
        palette: "mild",
        ramp: params.ramp || "default",
        strength: params.strength ?? 0.5,
      });
    } else {
      onParamsChange({
        ...params,
        style: "lego",
        palette: "classic",
      });
    }
  };

  return (
    <aside className="w-full lg:h-full lg:min-h-0 lg:overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden rounded-2xl border border-zinc-800/80 bg-zinc-900/60 p-4 sm:p-5 lg:p-4 backdrop-blur-md text-zinc-100 flex flex-col gap-5 sm:gap-6 lg:gap-3.5">
      <style>{`
        @keyframes fall-bit {
          0%   { transform: translateY(0) rotate(0deg); opacity: 1; }
          80%  { opacity: 1; }
          100% { transform: translateY(56px) rotate(var(--rot)); opacity: 0; }
        }
      `}</style>
      <div className="space-y-1.5">
        {isDone && onOpenDownload ? (
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <button
              type="button"
              onClick={onOpenDownload}
              className="h-11 flex items-center justify-center gap-2 px-4 rounded-xl font-bold text-xs tracking-wider bg-emerald-600 hover:bg-emerald-500 text-black shadow-emerald-500/20 transition-all active:scale-[0.98] cursor-pointer"
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
                  "h-11 px-4 rounded-xl text-xs font-medium transition-all border text-center",
                  isBusy
                    ? "opacity-40 cursor-not-allowed text-zinc-500 bg-zinc-900 border-zinc-800"
                    : isQuotaExhausted
                      ? "text-red-400 hover:text-red-300 bg-red-950/30 hover:bg-red-950/50 border-red-900/60 cursor-pointer"
                      : "text-zinc-400 hover:text-white bg-zinc-800/40 hover:bg-zinc-800 border-zinc-800 cursor-pointer",
                ].join(" ")}
              >
                {isBusy ? "Rendering..." : "Re-render"}
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
              "w-full h-11 px-4 rounded-xl font-bold text-xs tracking-wider transition-all flex items-center justify-center gap-2.5",
              isQuotaExhausted
                ? "bg-red-950/70 text-red-300 hover:bg-red-900/80 active:scale-[0.98] border border-red-800/80 cursor-pointer shadow-lg shadow-red-950/30"
                : canCreate && onCreateMosaic
                  ? "bg-white text-black hover:bg-zinc-200 active:scale-[0.98] shadow-lg shadow-white/10 cursor-pointer"
                  : "bg-zinc-800/70 text-zinc-500 cursor-not-allowed border border-zinc-800/80 opacity-60",
            ].join(" ")}
          >
            {isBusy ? (
              <>
                <span className="inline-block w-3.5 h-3.5 border-2 border-zinc-400 rounded-full animate-spin shrink-0" />
                <span>Rendering...</span>
              </>
            ) : isQuotaExhausted ? (
              <span>
                Limit reached (
                {Math.max(1, Math.ceil((quota?.resetsInSeconds ?? 0) / 60))}m
                reset)
              </span>
            ) : media ? (
              <span>Render {isAscii ? "ASCII" : "LEGO"}</span>
            ) : (
              <span>Upload to create</span>
            )}
          </button>
        )}

        <div className="flex justify-between items-center h-4 text-[10px] text-zinc-400">
          <span>Quota</span>
          <span
            className={`font-mono font-medium ${
              isQuotaExhausted ? "text-red-400 font-bold" : "text-emerald-400"
            }`}
          >
            {!media
              ? "—"
              : isVideo
                ? `${quota?.videos.remaining ?? 10}/${quota?.videos.limit ?? 10} videos left`
                : `${quota?.images.remaining ?? 30}/${quota?.images.limit ?? 30} images left`}
          </span>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium text-zinc-300 flex items-center justify-between">
          <span>Mosaic Style</span>
        </label>
        <div className="grid grid-cols-2 gap-1.5 p-1 rounded-xl bg-zinc-950/60 border border-zinc-800">
          <button
            type="button"
            onClick={() => handleStyleChange("lego")}
            disabled={disabled}
            className={[
              "py-2 text-xs relative overflow-hidden rounded-lg font-medium transition-all text-center flex items-center justify-center gap-2 cursor-pointer font-mono",
              params.style === "lego"
                ? "bg-white text-black shadow-sm font-semibold"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50",
            ].join(" ")}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 shadow-sm shrink-0" />
            <span>LEGO Studs</span>
            {renderBurst("lego")}
          </button>
          <button
            type="button"
            onClick={() => handleStyleChange("ascii")}
            disabled={disabled}
            className={[
              "py-2 text-xs relative overflow-hidden rounded-lg font-medium transition-all text-center flex items-center justify-center gap-2 cursor-pointer font-mono",
              params.style === "ascii"
                ? "bg-white text-black shadow-sm font-semibold"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50",
            ].join(" ")}
          >
            <span className="text-emerald-400 font-bold shrink-0 text-xs">
              #@
            </span>
            <span>ASCII Art</span>
            {renderBurst("ascii")}
          </button>
        </div>
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
            <span className="text-[11px] text-zinc-500">tiles</span>
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

      <div className="flex items-center justify-between gap-3">
        <label className="text-xs font-medium text-zinc-300 shrink-0">
          Tile Scale
        </label>
        <div className="flex gap-1 p-1 rounded-xl bg-zinc-950/60 border border-zinc-800">
          {TILE_SIZES.map((size) => (
            <button
              key={size}
              type="button"
              onClick={() => updateParam("tileSize", size)}
              disabled={disabled}
              className={[
                "px-2 py-1.5 text-xs rounded-lg font-mono font-medium transition-all cursor-pointer",
                params.tileSize === size
                  ? "bg-white text-black shadow-sm font-semibold"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50",
              ].join(" ")}
            >
              {size}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2" ref={paletteContainerRef}>
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-zinc-300">
            {isAscii ? "ASCII Palette" : "LEGO Color Palette"}
          </label>
        </div>

        <div className="relative">
          <button
            type="button"
            onClick={() => !disabled && setIsPaletteOpen((prev) => !prev)}
            disabled={disabled}
            aria-haspopup="listbox"
            aria-expanded={isPaletteOpen}
            className={[
              "w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl border text-left transition-colors duration-150 box-border",
              disabled
                ? "opacity-50 cursor-not-allowed bg-zinc-950/40 border-zinc-800"
                : isPaletteOpen
                  ? "cursor-pointer bg-zinc-950 border-zinc-500"
                  : "cursor-pointer bg-zinc-950/60 border-zinc-800 hover:border-zinc-700 hover:bg-zinc-950",
            ].join(" ")}
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="text-xs font-medium text-white truncate">
                {activePaletteObj?.name ?? params.palette}
              </span>
              <div className="flex gap-1 items-center shrink-0">
                {activePaletteObj?.colors.map((c, idx) => (
                  <span
                    key={idx}
                    className="w-2.5 h-2.5 rounded-full border border-black/40 shadow-sm shrink-0"
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
            </div>
            <svg
              className={`w-4 h-4 text-zinc-400 shrink-0 transition-transform duration-200 ${
                isPaletteOpen ? "rotate-180 text-white" : ""
              }`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>

          {isPaletteOpen && (
            <div
              className="absolute left-0 right-0 top-full mt-1.5 z-50 bg-zinc-900 border border-zinc-700/80 rounded-xl shadow-2xl p-1 max-h-56 overflow-y-auto custom-scrollbar backdrop-blur-md"
              role="listbox"
              tabIndex={-1}
            >
              {availablePalettes.map((pal) => {
                const isSelected = params.palette === pal.id;
                return (
                  <button
                    key={pal.id}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => {
                      updateParam("palette", pal.id);
                      setIsPaletteOpen(false);
                    }}
                    className={[
                      "w-full px-3 py-2 rounded-lg text-left flex items-center justify-between gap-3 text-xs transition-colors cursor-pointer",
                      isSelected
                        ? "bg-white/10 text-white font-medium"
                        : "text-zinc-300 hover:bg-zinc-800/70 hover:text-white",
                    ].join(" ")}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span className="truncate">{pal.name}</span>
                      <div className="flex gap-1 items-center shrink-0">
                        {pal.colors.map((c, idx) => (
                          <span
                            key={idx}
                            className="w-2 h-2 rounded-full border border-black/40 shadow-sm shrink-0"
                            style={{ backgroundColor: c }}
                          />
                        ))}
                      </div>
                    </div>
                    {isSelected && (
                      <svg
                        className="w-4 h-4 text-white shrink-0"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth="2.5"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {isAscii && (
        <div className="space-y-3 animate-in fade-in duration-200">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-zinc-300">
                Character Ramp
              </label>
            </div>
            <div className="grid grid-cols-5 gap-1 p-1 rounded-xl bg-zinc-950/60 border border-zinc-800">
              {ASCII_RAMPS.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => updateParam("ramp", r.id)}
                  disabled={disabled || !isAscii}
                  title={r.sample}
                  className={[
                    "py-1.5 text-[11px] sm:text-xs rounded-lg font-mono transition-colors text-center cursor-pointer truncate px-1",
                    (params.ramp || "default") === r.id
                      ? "bg-white text-black font-semibold shadow-sm"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50",
                  ].join(" ")}
                >
                  {r.name}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <label
              htmlFor="ascii-strength"
              className="text-xs font-medium text-zinc-300 shrink-0"
            >
              Tint Strength
            </label>
            <input
              id="ascii-strength"
              type="range"
              min={0.0}
              max={1.0}
              step={0.05}
              value={params.strength ?? 0.5}
              onChange={(e) => updateParam("strength", Number(e.target.value))}
              disabled={disabled || !isAscii}
              className="w-full"
            />
            <span className="text-xs font-mono text-zinc-400 shrink-0 w-9 text-right">
              {Math.round((params.strength ?? 0.5) * 100)}%
            </span>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <label className="text-xs font-medium text-zinc-300 shrink-0">
          Quality
        </label>
        <div className="flex gap-1 p-1 rounded-xl bg-zinc-950/60 border border-zinc-800">
          {QUALITIES.map((q) => (
            <button
              key={q.id}
              type="button"
              onClick={() => updateParam("quality", q.id)}
              disabled={disabled}
              title={q.desc}
              className={[
                "px-3 py-1.5 text-xs rounded-lg font-medium transition-all cursor-pointer",
                params.quality === q.id
                  ? "bg-white text-black shadow-sm font-semibold"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50",
              ].join(" ")}
            >
              {q.label}
            </button>
          ))}
        </div>
      </div>

      <div
        className={[
          "flex items-center justify-between gap-3 transition-opacity",
          isVideoOrGif ? "" : "opacity-40 pointer-events-none",
        ].join(" ")}
        aria-disabled={!isVideoOrGif}
        title={
          media?.type === "gif"
            ? "GIF max 30 FPS"
            : !isVideoOrGif
              ? "Video/GIF only"
              : undefined
        }
      >
        <label className="text-xs font-medium text-zinc-300 shrink-0">
          Frame Rate
        </label>
        <div className="flex gap-1 p-1 rounded-xl bg-zinc-950/60 border border-zinc-800">
          {(["original", "24", "30", "60"] as LegoFps[]).map((f) => {
            const isBlocked = media?.type === "gif" && f === "60";
            return (
              <button
                key={f}
                type="button"
                onClick={() => !isBlocked && updateParam("fps", f)}
                disabled={disabled || isBlocked || !isVideoOrGif}
                title={isBlocked ? "60 FPS not supported for GIF" : undefined}
                className={[
                  "px-2 py-1.5 text-xs rounded-lg font-mono transition-all",
                  params.fps === f && !isBlocked
                    ? "bg-white text-black font-medium shadow-sm"
                    : isBlocked
                      ? "opacity-30 cursor-not-allowed text-zinc-600 line-through"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 cursor-pointer",
                ].join(" ")}
              >
                {f === "original" ? "Orig" : f}
              </button>
            );
          })}
        </div>
      </div>

      <div
        className={[
          "space-y-2 transition-opacity",
          isVideo ? "" : "opacity-40 pointer-events-none",
        ].join(" ")}
        aria-disabled={!isVideo}
      >
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-zinc-300">
            Video Bitrate
          </label>
          <div className="flex gap-1 bg-zinc-950/80 p-0.5 rounded-lg border border-zinc-800 text-[10px]">
            <button
              type="button"
              disabled={!isVideo}
              onClick={() => updateParam("autoBitrate", true)}
              className={[
                "px-2 py-0.5 rounded transition-all cursor-pointer",
                params.autoBitrate
                  ? "bg-zinc-700 text-white font-medium"
                  : "text-zinc-400 hover:text-zinc-200",
              ].join(" ")}
            >
              Auto (~{autoBitrateRecommendedMbps} Mbps)
            </button>
            <button
              type="button"
              disabled={!isVideo}
              onClick={() => {
                if (isQuotaExhausted) {
                  onQuotaExceeded?.();
                  return;
                }
                onParamsChange({
                  ...params,
                  autoBitrate: false,
                  bitrateMbps: params.bitrateMbps || autoBitrateRecommendedMbps,
                });
              }}
              className={[
                "px-2 py-0.5 rounded transition-all cursor-pointer",
                !params.autoBitrate
                  ? "bg-zinc-700 text-white font-medium"
                  : "text-zinc-400 hover:text-zinc-200",
              ].join(" ")}
            >
              Custom
            </button>
          </div>
        </div>

        <div
          className={[
            "flex items-center gap-3",
            isVideo && !params.autoBitrate
              ? ""
              : "invisible pointer-events-none",
          ].join(" ")}
        >
          <span className="text-xs text-zinc-400 font-mono shrink-0">
            Target
          </span>
          <input
            type="range"
            min={0.5}
            max={12.0}
            step={0.5}
            value={params.bitrateMbps ?? autoBitrateRecommendedMbps}
            onChange={(e) => updateParam("bitrateMbps", Number(e.target.value))}
            disabled={disabled || !isVideo || params.autoBitrate}
            className="w-full"
          />
          <span className="text-xs text-zinc-400 font-mono shrink-0 w-16 text-right">
            {(params.bitrateMbps ?? autoBitrateRecommendedMbps).toFixed(1)} Mbps
          </span>
        </div>
      </div>

      {media && (
        <div className="rounded-xl bg-zinc-950/80 border border-zinc-800/90 p-3 space-y-2 text-xs">
          <div className="flex justify-between text-zinc-400">
            <span>Resolution</span>
            <div className="text-right">
              <span className="font-mono text-zinc-200">
                {outputWidth} × {outputHeight} px
              </span>
            </div>
          </div>
          {isVideo && isUpscaled && (
            <div className="flex items-center justify-between gap-1.5 p-2 rounded-lg bg-amber-950/30 border border-amber-800/40 text-[11px] text-amber-300">
              <span className="truncate">
                Upscaled {Math.round((outputWidth / sourceWidth) * 100)}% (
                {sourceWidth}×{sourceHeight})
              </span>
              {fittedTileSize !== params.tileSize && (
                <button
                  type="button"
                  onClick={() => updateParam("tileSize", fittedTileSize)}
                  className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 transition-all font-medium whitespace-nowrap cursor-pointer text-[10px]"
                >
                  Fit to {params.width * fittedTileSize}px
                </button>
              )}
            </div>
          )}
          <div className="flex justify-between text-zinc-400">
            <span>{isAscii ? "Grid Characters" : "Grid Studs"}</span>
            <span className="font-mono text-zinc-200">
              {params.width} × {gridHeight} ({totalUnits.toLocaleString()})
            </span>
          </div>
        </div>
      )}
    </aside>
  );
}
