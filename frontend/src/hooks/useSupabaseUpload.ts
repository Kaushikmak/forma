import { useState } from "react";
import type { LocalMediaFile, RemoteAsset } from "../types/types";
import { getOrCreateDeviceId } from "../utils/device";

interface UploadSlotResponse {
  assetId: string;
  uploadUrl: string;
  expiresAt: number;
}

interface UseSupabaseUploadOptions {
  apiBaseUrl: string;
}

export function useSupabaseUpload({ apiBaseUrl }: UseSupabaseUploadOptions) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setUploading(false);
    setProgress(0);
    setError(null);
  };

  const requestUploadSlot = async (
    media: LocalMediaFile,
  ): Promise<UploadSlotResponse> => {
    const baseUrl = apiBaseUrl ? apiBaseUrl.replace(/\/$/, "") : "";
    const deviceId = getOrCreateDeviceId();
    const response = await fetch(`${baseUrl}/api/upload-slot`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Device-Id": deviceId,
      },
      body: JSON.stringify({
        fileSize: media.sizeBytes,
        mimeType: media.mimeType,
        width: media.width,
        height: media.height,
        durationSec: media.durationSec,
      }),
    });

    if (!response.ok) {
      const message = await response.text();

      throw new Error(message || "Failed to create upload slot.");
    }

    return response.json();
  };

  const uploadFile = (uploadUrl: string, file: File): Promise<void> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.open("PUT", uploadUrl);

      xhr.setRequestHeader("Content-Type", file.type);

      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) {
          return;
        }

        const percentage = (event.loaded / event.total) * 100;

        setProgress(percentage);
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          setProgress(100);
          resolve();
        } else {
          reject(new Error(`Upload failed with status ${xhr.status}.`));
        }
      };

      xhr.onerror = () => {
        reject(new Error("Network error during upload."));
      };

      xhr.onabort = () => {
        reject(new Error("Upload cancelled."));
      };

      xhr.send(file);
    });
  };

  const upload = async (media: LocalMediaFile): Promise<RemoteAsset | null> => {
    if (uploading) {
      return null;
    }

    setUploading(true);
    setProgress(0);
    setError(null);

    try {
      const slot = await requestUploadSlot(media);
      const baseUrl = apiBaseUrl ? apiBaseUrl.replace(/\/$/, "") : "";
      const fullUploadUrl = slot.uploadUrl.startsWith("http")
        ? slot.uploadUrl
        : `${baseUrl}${slot.uploadUrl.startsWith("/") ? "" : "/"}${slot.uploadUrl}`;
      await uploadFile(fullUploadUrl, media.file);

      return {
        assetId: slot.assetId,
        expiresAt: slot.expiresAt,
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed.";

      setError(message);

      return null;
    } finally {
      setUploading(false);
    }
  };

  return {
    upload,
    uploading,
    progress,
    error,
    reset,
  };
}
