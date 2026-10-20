import { useState } from "react";
import type { LocalMediaFile } from "../types/types";

const MAX_FILE_SIZE = 50 * 1024 * 1024;

const ACCEPTED_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
  "image/bmp",
  "image/tiff",
  "video/mp4",
  "video/webm",
  "video/quicktime",
  "video/x-msvideo",
]);

export function useMediaInspector() {
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * validate file for it's size and type
   * @param file
   * @returns error string
   */
  const validateFile = (file: File): string | null => {
    if (file.size > MAX_FILE_SIZE) {
      return "File too large. Maximum file size is 50 MB.";
    }

    if (!ACCEPTED_TYPES.has(file.type)) {
      return `Unsupported file type: ${file.type || "unknown"}`;
    }

    return null;
  };

  /**
   * Inspect local image and gif file to extract it's metadata
   * and generates temporary object url for previewing
   * @param {File} file
   * @returns {Promise<LocalMediaFile>}
   */
  const inspectImage = (file: File): Promise<LocalMediaFile> => {
    return new Promise((resolve, reject) => {
      const previewUrl = URL.createObjectURL(file);
      const image = new Image();

      image.onload = () => {
        resolve({
          file,
          previewUrl,
          mimeType: file.type,
          sizeBytes: file.size,
          type: file.type === "image/gif" ? "gif" : "image",
          width: image.naturalWidth,
          height: image.naturalHeight,
        });
      };

      image.onerror = () => {
        URL.revokeObjectURL(previewUrl);
        reject(new Error("Unable to read image."));
      };

      image.src = previewUrl;
    });
  };

  /**
   * Inspect local video file to extract it's metadata
   * and generates temporary object url for previewing
   * @param {File} file
   * @returns {Promise<LocalMediaFile>}
   */
  const inspectVideo = (file: File): Promise<LocalMediaFile> => {
    return new Promise((resolve, reject) => {
      const previewUrl = URL.createObjectURL(file);
      const video = document.createElement("video");

      video.preload = "metadata";

      video.onloadedmetadata = () => {
        resolve({
          file,
          previewUrl,
          mimeType: file.type,
          sizeBytes: file.size,
          type: "video",
          width: video.videoWidth,
          height: video.videoHeight,
          durationSec: video.duration,
        });
      };

      video.onerror = () => {
        URL.revokeObjectURL(previewUrl);
        reject(new Error("Unable to read video."));
      };

      video.src = previewUrl;
    });
  };

  const inspect = async (file: File): Promise<LocalMediaFile | null> => {
    setError(null);

    const validationError = validateFile(file);

    if (validationError) {
      setError(validationError);
      return null;
    }

    setLoading(true);

    try {
      if (file.type.startsWith("image/")) {
        return await inspectImage(file);
      }

      if (file.type.startsWith("video/")) {
        return await inspectVideo(file);
      }

      throw new Error("Unsupported media type.");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to inspect media.";

      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  };

  return {
    inspect,
    loading,
    error,
  };
}
