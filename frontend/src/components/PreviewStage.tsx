import React, { useRef, useState, useEffect } from "react";
import type { JobState, LegoParams, LocalMediaFile } from "../types/types";
import { useMediaInspector } from "../hooks/useMediaInspector";
import { getStageTitle, getStageDescription } from "../utils/loaderutil";

interface PreviewStageProps {
  media: LocalMediaFile;
  params: LegoParams;
  job: JobState;
  isRendering?: boolean;
  onMediaSelect: (media: LocalMediaFile) => void;
  onOpenDownload?: () => void;
  onClearMedia?: () => void;
}

export default function PreviewStage({
  media,
  job,
  isRendering = false,
  onMediaSelect,
  onOpenDownload,
  onClearMedia,
}: PreviewStageProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const lastTimeRef = useRef(0);

  const { inspect, loading, error } = useMediaInspector();
  const [userSelectedView, setUserSelectedView] = useState<
    "mosaic" | "original" | null
  >(null);

  // Smooth video playback buffer & blob cache state
  const [videoBlobUrl, setVideoBlobUrl] = useState<string | null>(null);
  const [isBufferingBlob, setIsBufferingBlob] = useState(false);
  const [blobBufferProgress, setBlobBufferProgress] = useState(0);
  const [isWaitingForBuffer, setIsWaitingForBuffer] = useState(false);

  const hasResult = Boolean(job?.resultUrl);
  const viewMode = userSelectedView ?? (hasResult ? "mosaic" : "original");

  const handleFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    if (file) {
      const newMedia = await inspect(file);
      if (newMedia) {
        setUserSelectedView(null);
        onMediaSelect(newMedia);
      }
    }
    event.target.value = "";
  };

  const isBusy =
    job?.status !== "done" &&
    job?.status !== "failed" &&
    job?.status !== "rejected" &&
    job?.status !== "cancelled" &&
    job?.status !== "error" &&
    (isRendering ||
      job?.status === "uploading" ||
      job?.status === "queued" ||
      job?.status === "probing" ||
      job?.status === "processing" ||
      job?.status === "encoding");

  const showingMosaic = hasResult && viewMode === "mosaic";

  useEffect(() => {
    if (!job?.resultUrl || media.type !== "video") {
      return;
    }

    let isCancelled = false;
    let createdUrl: string | null = null;

    const bufferVideo = async () => {
      try {
        setIsBufferingBlob(true);
        setBlobBufferProgress(0);

        const response = await fetch(job.resultUrl!);
        if (!response.ok) {
          throw new Error(`Failed to fetch video: ${response.statusText}`);
        }

        const contentLength = response.headers.get("content-length");
        const totalBytes = contentLength ? parseInt(contentLength, 10) : 0;

        if (!response.body || !totalBytes) {
          const blob = await response.blob();
          if (!isCancelled) {
            createdUrl = URL.createObjectURL(blob);
            setVideoBlobUrl(createdUrl);
            setIsBufferingBlob(false);
          }
          return;
        }

        const reader = response.body.getReader();
        const chunks: Uint8Array[] = [];
        let receivedBytes = 0;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (value) {
            chunks.push(value);
            receivedBytes += value.length;
            if (totalBytes > 0) {
              setBlobBufferProgress(
                Math.round((receivedBytes / totalBytes) * 100),
              );
            }
          }
        }

        if (!isCancelled) {
          const blob = new Blob(chunks as BlobPart[], { type: "video/mp4" });
          createdUrl = URL.createObjectURL(blob);
          setVideoBlobUrl(createdUrl);
          setIsBufferingBlob(false);
        }
      } catch (err) {
        console.warn(
          "Direct blob buffering failed, falling back to direct stream:",
          err,
        );
        if (!isCancelled) {
          setIsBufferingBlob(false);
          setVideoBlobUrl(null);
        }
      }
    };

    bufferVideo();

    return () => {
      isCancelled = true;
      setVideoBlobUrl(null);
      setIsBufferingBlob(false);
      setBlobBufferProgress(0);
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl);
      }
    };
  }, [job?.resultUrl, media.type]);

  return (
    <div className="flex flex-col items-center w-full">
      <input
        ref={inputRef}
        type="file"
        accept=".jpg,.jpeg,.png,.webp,.gif,.bmp,.tiff,.mp4,.webm,.mov,.avi"
        onChange={handleFileChange}
        hidden
        disabled={loading}
      />

      <div className="relative w-full min-h-[260px] sm:min-h-[380px] max-h-[55dvh] sm:max-h-[520px] flex items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-950/80 p-2.5 sm:p-3 overflow-hidden shadow-2xl group">
        <div className="max-h-[50dvh] sm:max-h-[480px] flex items-center justify-center overflow-hidden rounded-xl">
          {media.type === "video" ? (
            <div className="relative flex items-center justify-center">
              <video
                ref={videoRef}
                key={showingMosaic ? "mosaic-video" : "original-video"}
                src={
                  showingMosaic
                    ? videoBlobUrl || job?.resultUrl || media.previewUrl
                    : media.previewUrl
                }
                controls
                autoPlay={showingMosaic}
                loop
                playsInline
                preload="auto"
                onWaiting={() => setIsWaitingForBuffer(true)}
                onPlaying={() => setIsWaitingForBuffer(false)}
                onCanPlay={() => setIsWaitingForBuffer(false)}
                onTimeUpdate={(e) => {
                  lastTimeRef.current = e.currentTarget.currentTime;
                }}
                onLoadedMetadata={(e) => {
                  if (lastTimeRef.current > 0 && showingMosaic) {
                    try {
                      e.currentTarget.currentTime = lastTimeRef.current;
                    } catch {
                      // ignore if not seekable yet
                    }
                  }
                }}
                className={[
                  "max-h-[50dvh] sm:max-h-[480px] w-auto max-w-full rounded-lg object-contain",
                  isBusy
                    ? "blur-md brightness-75 scale-[0.98] transition-all duration-300"
                    : "transition-all duration-300",
                ].join(" ")}
              />

              {isWaitingForBuffer && !isBusy && !videoBlobUrl && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/40 backdrop-blur-[2px] pointer-events-none transition-all duration-200 z-10">
                  <div className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-full bg-zinc-900/90 border border-zinc-700/80 text-xs text-white shadow-2xl">
                    <span className="w-3.5 h-3.5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin shrink-0" />
                    <span className="font-medium font-sans">
                      Buffering stream...
                    </span>
                  </div>
                </div>
              )}

              {isBufferingBlob &&
                showingMosaic &&
                blobBufferProgress > 0 &&
                blobBufferProgress < 100 && (
                  <div className="absolute bottom-14 left-1/2 -translate-x-1/2 z-20 pointer-events-none transition-all animate-in fade-in duration-200">
                    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-zinc-950/85 backdrop-blur-md border border-zinc-800 text-[11px] text-zinc-300 shadow-lg">
                      <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0" />
                      <span className="font-mono">
                        Caching for smooth playback: {blobBufferProgress}%
                      </span>
                    </div>
                  </div>
                )}
            </div>
          ) : (
            <img
              src={
                showingMosaic && job?.resultUrl
                  ? job.resultUrl
                  : media.previewUrl
              }
              alt={showingMosaic ? "LEGO Mosaic Result" : "Media Preview"}
              className={[
                "max-h-[50dvh] sm:max-h-[480px] w-auto max-w-full rounded-lg object-contain select-none",
                isBusy
                  ? "blur-md brightness-75 scale-[0.98] transition-all duration-300"
                  : "transition-all duration-300",
              ].join(" ")}
            />
          )}

          {isBusy && (
            <div className="absolute inset-0 flex flex-col items-center justify-center p-3 sm:p-4 z-30 pointer-events-none">
              <div className="flex flex-col items-center gap-2.5 px-4 sm:px-6 py-3.5 sm:py-4 rounded-2xl bg-zinc-950/90 backdrop-blur-xl border border-zinc-700/80 shadow-2xl text-center max-w-[90vw] sm:max-w-sm w-full animate-in fade-in zoom-in-95 duration-200">
                <div className="flex items-center gap-2.5 text-amber-400">
                  <span className="inline-block w-4 h-4 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin shrink-0" />
                  <span className="text-xs font-semibold tracking-wider text-white uppercase font-mono">
                    {getStageTitle(job?.status ?? "processing")}
                  </span>
                </div>
                <p className="text-[11px] text-zinc-300 text-center leading-relaxed font-sans px-1">
                  {getStageDescription(
                    job?.status ?? "processing",
                    job?.errorMessage,
                  )}
                </p>

                <div className="w-full space-y-1 pt-0.5">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-amber-400 font-semibold">
                      {Math.round(job?.progress ?? 0)}%
                    </span>
                    <span className="text-[10px] text-zinc-500 uppercase tracking-wider">
                      {job?.status}
                    </span>
                  </div>

                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800/80">
                    <div
                      className="h-full rounded-full bg-amber-400 transition-all duration-300 ease-out"
                      style={{
                        width: `${Math.min(Math.max(job?.progress ?? 5, 5), 100)}%`,
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="absolute top-3 right-3 sm:top-5 sm:right-5 flex items-center gap-1.5 sm:gap-2 z-20">
          {hasResult && (
            <>
              <div className="flex items-center rounded-full bg-black/75 backdrop-blur-md border border-white/10 p-0.5 text-[11px]">
                <button
                  type="button"
                  onClick={() => setUserSelectedView("mosaic")}
                  className={[
                    "px-2.5 py-1 rounded-full font-medium transition-all",
                    showingMosaic
                      ? "bg-white text-black font-semibold shadow-sm"
                      : "text-zinc-400 hover:text-white",
                  ].join(" ")}
                >
                  Mosaic
                </button>
                <button
                  type="button"
                  onClick={() => setUserSelectedView("original")}
                  className={[
                    "px-2.5 py-1 rounded-full font-medium transition-all",
                    !showingMosaic
                      ? "bg-white text-black font-semibold shadow-sm"
                      : "text-zinc-400 hover:text-white",
                  ].join(" ")}
                >
                  Original
                </button>
              </div>

              {onOpenDownload && (
                <button
                  type="button"
                  onClick={onOpenDownload}
                  className="flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold bg-emerald-500 hover:bg-emerald-400 text-black shadow-lg shadow-emerald-500/20 transition-all active:scale-95"
                >
                  <svg
                    className="w-3.5 h-3.5"
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
              )}
            </>
          )}
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between w-full px-1 text-xs text-zinc-400">
        <div className="flex items-center gap-3">
          {onClearMedia && (
            <button
              type="button"
              onClick={onClearMedia}
              disabled={loading || isBusy}
              className="text-xs text-zinc-500 hover:text-red-400 transition-colors disabled:opacity-40"
            >
              Remove
            </button>
          )}
          <button
            type="button"
            onClick={() => !loading && inputRef.current?.click()}
            disabled={loading || isBusy}
            className="text-xs text-zinc-400 hover:text-white underline underline-offset-2 transition-colors disabled:opacity-40"
          >
            {loading ? "Reading..." : "Replace media"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-2 w-full px-3 py-2 rounded-xl bg-red-950/40 border border-red-900/60 text-xs text-red-300">
          {error}
        </div>
      )}

      {job.errorMessage && (
        <div className="flex-col items-start mt-2 w-full px-3 py-2 rounded-xl bg-red-950/40 border border-red-900/60 text-xs text-red-300 flex justify-between">
          <span>{job.errorMessage}</span>
          <span className="underline">
            My cloud bill is already threatening me, please bear with me until I
            get good VPS
          </span>
          <span>F#ck these big corps man</span>
        </div>
      )}
    </div>
  );
}
