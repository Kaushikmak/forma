import { useState, useEffect, useCallback } from "react";
import { getOrCreateDeviceId } from "../utils/device";

export interface QuotaBucket {
  limit: number;
  used: number;
  remaining: number;
}

export interface QuotaData {
  deviceId: string;
  images: QuotaBucket;
  videos: QuotaBucket;
  windowStart: number;
  resetAt: number;
  resetsInSeconds: number;
}

export function useQuota() {
  const [quota, setQuota] = useState<QuotaData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchQuota = useCallback(async () => {
    try {
      setLoading(true);
      const deviceId = getOrCreateDeviceId();
      const res = await fetch("/api/quota", {
        headers: {
          "X-Device-Id": deviceId,
        },
      });
      if (!res.ok) {
        throw new Error("Failed to fetch quota");
      }
      const data: QuotaData = await res.json();
      setQuota(data);
      setError(null);
      return data;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Quota fetch failed";
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;

    async function syncQuota() {
      try {
        const deviceId = getOrCreateDeviceId();
        const res = await fetch("/api/quota", {
          headers: {
            "X-Device-Id": deviceId,
          },
        });
        if (!res.ok) {
          throw new Error("Failed to fetch quota");
        }
        const data: QuotaData = await res.json();
        if (!ignore) {
          setQuota(data);
          setError(null);
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : "Quota fetch failed");
        }
      }
    }

    void syncQuota();

    // Poll periodically to keep timer & quota in sync
    const timer = setInterval(() => {
      void syncQuota();
    }, 30000);

    return () => {
      ignore = true;
      clearInterval(timer);
    };
  }, []);

  return {
    quota,
    loading,
    error,
    refreshQuota: fetchQuota,
  };
}
