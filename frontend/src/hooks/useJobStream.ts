import { useEffect, useState, useRef } from "react";
import type { JobStatus } from "../types/types";

interface JobStreamEvent {
  status?: JobStatus;
  progress?: number;
  resultUrl?: string;
  errorMessage?: string;
}

interface UseJobStreamOptions {
  apiBaseUrl: string;
  jobId: string | null;
}

const TERMINAL_STATUSES = new Set<string>([
  "done",
  "error",
  "rejected",
  "failed",
  "cancelled",
  "expired",
]);

export function useJobStream({ apiBaseUrl, jobId }: UseJobStreamOptions) {
  const [currentJobId, setCurrentJobId] = useState<string | null>(jobId);
  const [status, setStatus] = useState<JobStatus>(jobId ? "queued" : "idle");
  const [progress, setProgress] = useState(0);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (jobId !== currentJobId) {
    setCurrentJobId(jobId);
    setStatus(jobId ? "queued" : "idle");
    setProgress(0);
    setError(null);
    if (!jobId) {
      setResultUrl(null);
    }
  }

  const isClosedRef = useRef(false);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    isClosedRef.current = false;
    const baseUrl = apiBaseUrl ? apiBaseUrl.replace(/\/$/, "") : "";

    const eventSource = new EventSource(`${baseUrl}/api/jobs/${jobId}/events`);

    const handlePayload = (data: JobStreamEvent) => {
      if (data.status) {
        setStatus(data.status);
      }
      if (typeof data.progress === "number") {
        setProgress(data.progress);
      }
      if (data.resultUrl) {
        const fullResultUrl = data.resultUrl.startsWith("http")
          ? data.resultUrl
          : `${baseUrl}${data.resultUrl.startsWith("/") ? "" : "/"}${data.resultUrl}`;
        setResultUrl(fullResultUrl);
      }
      if (data.errorMessage) {
        setError(data.errorMessage);
      }
      if (data.status && TERMINAL_STATUSES.has(data.status)) {
        isClosedRef.current = true;
        eventSource.close();
      }
    };

    eventSource.onopen = () => {
      // Only set to queued if not already terminal
      if (!isClosedRef.current) {
        setStatus((prev) => (TERMINAL_STATUSES.has(prev) ? prev : "queued"));
      }
    };

    eventSource.onmessage = (event) => {
      try {
        const data: JobStreamEvent = JSON.parse(event.data);
        handlePayload(data);
      } catch {
        setError("Received invalid job update.");
      }
    };

    eventSource.onerror = () => {
      if (isClosedRef.current) {
        eventSource.close();
      }
    };

    const pollInterval = setInterval(async () => {
      if (isClosedRef.current) {
        clearInterval(pollInterval);
        return;
      }
      try {
        const res = await fetch(`${baseUrl}/api/jobs/${jobId}`);
        if (res.ok) {
          const jobData = await res.json();
          handlePayload(jobData);
          if (jobData.status && TERMINAL_STATUSES.has(jobData.status)) {
            clearInterval(pollInterval);
          }
        }
      } catch {
        // ignore network hiccups
      }
    }, 1200);

    return () => {
      isClosedRef.current = true;
      clearInterval(pollInterval);
      eventSource.close();
    };
  }, [apiBaseUrl, jobId]);

  return {
    status: jobId ? status : "idle",
    progress: jobId ? progress : 0,
    resultUrl: jobId ? resultUrl : null,
    error: jobId ? error : null,
  };
}
