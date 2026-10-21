import { useState, useRef, useEffect, useCallback } from "react";
import ControlsSidebar from "./components/ControlsSidebar";
import DownloadModal from "./components/DownloadModal";
import MediaDropzone from "./components/MediaDropzone";
import PreviewStage from "./components/PreviewStage";
import QuotaToast from "./components/QuotaToast";
import { useJobStream } from "./hooks/useJobStream";
import { useQuota } from "./hooks/useQuota";
import { useSupabaseUpload } from "./hooks/useSupabaseUpload";
import type {
  JobState,
  JobStatus,
  LegoParams,
  LocalMediaFile,
} from "./types/types";
import { getOrCreateDeviceId } from "./utils/device";

const DEFAULT_PARAMS: LegoParams = {
  style: "lego",
  width: 64,
  tileSize: 16,
  palette: "classic",
  quality: "high",
  fps: "original",
  autoBitrate: true,
  bitrateMbps: 4.0,
};

const INITIAL_JOB_STATE: JobState = {
  jobId: null,
  status: "idle",
  progress: 0,
  resultUrl: null,
  errorMessage: null,
};

function App() {
  const [media, setMedia] = useState<LocalMediaFile | null>(null);
  const [params, setParams] = useState<LegoParams>(DEFAULT_PARAMS);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [uploadedAsset, setUploadedAsset] = useState<{
    assetId: string;
    expiresAt: number;
  } | null>(null);
  const [localJobStatus, setLocalJobStatus] = useState<JobStatus | null>(null);
  const [localJobError, setLocalJobError] = useState<string | null>(null);
  const [downloadModalOpen, setDownloadModalOpen] = useState(false);

  const { quota, refreshQuota } = useQuota();
  const [quotaToastOpen, setQuotaToastOpen] = useState(false);
  const [quotaPressCount, setQuotaPressCount] = useState(0);

  const handleQuotaExceeded = useCallback(() => {
    setQuotaPressCount((prev) => prev + 1);
    setQuotaToastOpen(true);
  }, []);

  const lastDispatchedParamsRef = useRef<string>("");

  const {
    upload,
    uploading,
    progress: uploadProgress,
    error: uploadError,
    reset: resetUpload,
  } = useSupabaseUpload({
    apiBaseUrl: "",
  });

  const stream = useJobStream({
    apiBaseUrl: "",
    jobId: activeJobId,
  });

  useEffect(() => {
    if (
      stream.status === "done" ||
      stream.status === "failed" ||
      stream.status === "rejected" ||
      stream.status === "cancelled"
    ) {
      refreshQuota();
    }
  }, [stream.status, refreshQuota]);

  const isLiveRendering =
    uploading ||
    localJobStatus === "uploading" ||
    (activeJobId
      ? stream.status !== "done" &&
        stream.status !== "failed" &&
        stream.status !== "rejected" &&
        stream.status !== "cancelled" &&
        stream.status !== "error" &&
        stream.status !== "idle"
      : localJobStatus === "queued");

  // Derived reactive job state
  const job: JobState = activeJobId
    ? {
        jobId: activeJobId,
        status: stream.status,
        progress: stream.progress,
        resultUrl: stream.resultUrl,
        errorMessage: stream.error || localJobError,
      }
    : uploading
      ? {
          jobId: null,
          status: "uploading",
          progress: Math.min(Math.round(uploadProgress * 0.9), 90),
          resultUrl: null,
          errorMessage: null,
        }
      : localJobStatus
        ? {
            jobId: null,
            status: localJobStatus,
            progress: localJobStatus === "queued" ? 5 : 0,
            resultUrl: null,
            errorMessage: localJobError,
          }
        : INITIAL_JOB_STATE;

  const handleMediaSelect = (selectedMedia: LocalMediaFile) => {
    if (media) {
      URL.revokeObjectURL(media.previewUrl);
    }
    setMedia(selectedMedia);
    setUploadedAsset(null);
    setActiveJobId(null);
    setLocalJobStatus(null);
    setLocalJobError(null);
    lastDispatchedParamsRef.current = "";
    setQuotaPressCount(0);
    setQuotaToastOpen(false);

    // If it's a video with <= 720p width, adapt default tile size to prevent huge upscaling
    if (selectedMedia.type === "video" && selectedMedia.width <= 720) {
      setParams((prev) => ({
        ...prev,
        tileSize: prev.tileSize > 12 ? 12 : prev.tileSize,
      }));
    }
  };

  const handleClearMedia = () => {
    if (media) {
      URL.revokeObjectURL(media.previewUrl);
    }
    setMedia(null);
    setUploadedAsset(null);
    setActiveJobId(null);
    setLocalJobStatus(null);
    setLocalJobError(null);
    lastDispatchedParamsRef.current = "";
    setQuotaPressCount(0);
    setQuotaToastOpen(false);
    resetUpload();
  };

  const dispatchJob = useCallback(
    async (assetId: string, currentParams: LegoParams) => {
      setLocalJobError(null);

      try {
        const deviceId = getOrCreateDeviceId();

        // Calculate web-optimized bitrate if autoBitrate is on for video
        let resolvedBitrate: number | undefined = undefined;
        if (media?.type === "video") {
          if (currentParams.autoBitrate) {
            if (media.sizeBytes && media.durationSec && media.durationSec > 0) {
              const srcBitrate =
                (media.sizeBytes * 8) / (media.durationSec * 1_000_000);
              // Respect source bitrate: allow ~1.15x margin for mosaic rendering, capped to 4.0 Mbps max for smooth web streaming
              resolvedBitrate = Math.min(
                Math.max(Number((srcBitrate * 1.15).toFixed(1)), 1.5),
                4.0,
              );
            } else {
              resolvedBitrate = 3.0;
            }
          } else {
            resolvedBitrate = currentParams.bitrateMbps;
          }
        }

        const response = await fetch("/api/jobs", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Device-Id": deviceId,
          },
          body: JSON.stringify({
            style: "lego",
            input: {
              storageKey: `uploads/${assetId}/input`,
              assetId,
            },
            params: {
              style: "lego",
              width: currentParams.width,
              tileSize: currentParams.tileSize,
              palette: currentParams.palette,
              quality: currentParams.quality,
              fps: currentParams.fps,
              bitrateMbps: resolvedBitrate,
            },
          }),
        });

        if (!response.ok) {
          const errText = await response.text();
          let message = errText;
          try {
            const jsonErr = JSON.parse(errText);
            message = jsonErr.errorMessage || jsonErr.error || errText;
          } catch {
            // keep errText
          }
          setLocalJobError(message);
          setLocalJobStatus(null);
          return;
        }

        const jobData = await response.json();
        lastDispatchedParamsRef.current = JSON.stringify(currentParams);
        setActiveJobId(jobData.jobId);
        setLocalJobStatus(null);
        refreshQuota();
      } catch (err) {
        setLocalJobError(
          err instanceof Error ? err.message : "Failed to dispatch mosaic job.",
        );
        setLocalJobStatus(null);
      }
    },
    [refreshQuota, media],
  );

  const handleCreateMosaic = async () => {
    if (!media || isLiveRendering) return;

    let asset = uploadedAsset;
    if (!asset) {
      setLocalJobStatus("uploading");
      setLocalJobError(null);

      const uploaded = await upload(media);
      if (!uploaded) {
        setLocalJobStatus("error");
        setLocalJobError(uploadError || "Failed to upload media.");
        return;
      }
      asset = uploaded;
      lastDispatchedParamsRef.current = JSON.stringify(params);
      setUploadedAsset(uploaded);
    }

    lastDispatchedParamsRef.current = JSON.stringify(params);
    setLocalJobStatus("queued");
    await dispatchJob(asset.assetId, params);
  };

  const isVideo = media?.type === "video";
  const remainingQuota = quota
    ? isVideo
      ? quota.videos.remaining
      : quota.images.remaining
    : undefined;
  const isQuotaExhausted = remainingQuota !== undefined && remainingQuota <= 0;

  useEffect(() => {
    if (!media || !uploadedAsset || !lastDispatchedParamsRef.current) return;

    const paramsKey = JSON.stringify(params);
    if (paramsKey === lastDispatchedParamsRef.current) return;

    if (isQuotaExhausted) return;

    const timer = setTimeout(() => {
      if (paramsKey === lastDispatchedParamsRef.current || isQuotaExhausted)
        return;
      lastDispatchedParamsRef.current = paramsKey;
      setLocalJobStatus("queued");
      dispatchJob(uploadedAsset.assetId, params);
    }, 500);

    return () => clearTimeout(timer);
  }, [params, uploadedAsset, media, isQuotaExhausted, dispatchJob]);

  return (
    <div className="min-h-screen min-h-dvh bg-zinc-950 text-zinc-100 flex flex-col justify-between selection:bg-white selection:text-black">
      <header className="border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md sticky top-0 z-40 px-4 sm:px-6 py-3 sm:py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <a href="/">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-black tracking-wider uppercase m-0 p-0 flex">
                <span className="text-red-500 drop-shadow-[0_2px_0_#000]">F</span>
                <span className="text-yellow-400 drop-shadow-[0_2px_0_#000]">
                  o
                </span>
                <span className="text-blue-500 drop-shadow-[0_2px_0_#000]">
                  r
                </span>
                <span className="text-green-500 drop-shadow-[0_2px_0_#000]">
                  m
                </span>
                <span className="text-red-500 drop-shadow-[0_2px_0_#000]">a</span>
              </h1>
            </div>
          </a>
        </div>

        {quota && (
          <div
            className="flex-col items-center gap-2 sm:gap-3 text-xs px-2.5 sm:px-3 py-1 rounded-full bg-zinc-900/90 border border-zinc-800 text-zinc-300 opacity-60"
            title={`Quota resets in ${Math.max(1, Math.ceil(quota.resetsInSeconds / 60))} minutes`}
          >
            <span className="flex items-center gap-1.5 font-mono">
              <span className="text-zinc-500 text-[10px] tracking-wider  font-medium">
                credit
              </span>
              <span
                className={
                  quota.images.remaining <= 3
                    ? "text-red-400 font-bold"
                    : "text-emerald-400 font-medium"
                }
              >
                {quota.images.remaining + quota.videos.remaining}/{quota.images.limit + quota.videos.limit}
              </span>
            </span>
            <span className="text-zinc-500 text-[11px] hidden sm:inline font-mono">
              refill in: ({Math.max(1, Math.ceil(quota.resetsInSeconds / 60))}m)
            </span>
          </div>
        )}
      </header>


      <main className="flex-1 max-w-7xl w-full mx-auto p-3 sm:p-6 lg:p-8 flex flex-col justify-start lg:justify-center">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 sm:gap-6 lg:gap-8 items-start">
          <section className="lg:col-span-7 xl:col-span-8 flex flex-col items-center justify-center min-h-[300px] sm:min-h-[460px]">
            {!media ? (
              <div className="w-full max-w-xl">
                <MediaDropzone onMediaSelect={handleMediaSelect} />
              </div>
            ) : (
              <div className="w-full">
                <PreviewStage
                  media={media}
                  params={params}
                  job={job}
                  isRendering={isLiveRendering}
                  onMediaSelect={handleMediaSelect}
                  onOpenDownload={() => setDownloadModalOpen(true)}
                  onClearMedia={handleClearMedia}
                />
              </div>
            )}
          </section>

          <section className="lg:col-span-5 xl:col-span-4">
            <ControlsSidebar
              media={media}
              params={params}
              onParamsChange={setParams}
              disabled={!media || uploading}
              job={job}
              isRendering={isLiveRendering}
              quota={quota}
              onCreateMosaic={handleCreateMosaic}
              onOpenDownload={() => setDownloadModalOpen(true)}
              onQuotaExceeded={handleQuotaExceeded}
            />
          </section>
        </div>
      </main>

      <footer className="border-t border-zinc-900 px-4 sm:px-6 py-4 text-center text-xs text-zinc-600 font-mono">
        <p className="text-sm text-zinc-500">
          This <span className="inline-block">💩</span> made by{" "}
          <a
            target="_blank"
            className="underline decoration-2 decoration-gray-500"
            href="https://github.com/Kaushikmak"
          >
            tasty-taco
          </a>{" "}
          <span className="inline-block">🌮</span>
        </p>
      </footer>
      {media && job.resultUrl && (
        <DownloadModal
          isOpen={downloadModalOpen}
          onClose={() => setDownloadModalOpen(false)}
          media={media}
          params={params}
          resultUrl={job.resultUrl}
        />
      )}

      <QuotaToast
        isOpen={quotaToastOpen}
        onClose={() => setQuotaToastOpen(false)}
        clickCount={quotaPressCount}
      />
    </div>
  );
}

export default App;
