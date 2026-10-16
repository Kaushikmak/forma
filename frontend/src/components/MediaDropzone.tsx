import React, { useRef, useState } from "react";
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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const validateFile = (file: File): string | null => {
    if (file.size > MAX_FILE_SIZE) {
      return "File too large. Maximum file size is 50 MB.";
    }

    if (!ACCEPTED_TYPES.has(file.type)) {
      return `Unsupported file type: ${file.type || "unknown"}`;
    }

    return null;
  };

  const getImageMetadata = (file: File): Promise<LocalMediaFile> => {
    return new Promise((resolve, reject) => {
      const previewUrl = URL.createObjectURL(file);
      const image = new Image();

      image.onload = () => {
        const type = file.type === "image/gif" ? "gif" : "image";

        resolve({
          file,
          previewUrl,
          sizeBytes: file.size,
          type,
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

  const getVideoMetadata = (file: File): Promise<LocalMediaFile> => {
    return new Promise((resolve, reject) => {
      const previewUrl = URL.createObjectURL(file);
      const video = document.createElement("video");

      video.preload = "metadata";

      video.onloadedmetadata = () => {
        resolve({
          file,
          previewUrl,
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

  const processFile = async (file: File) => {
    if (disabled || loading) {
      return;
    }

    setError(null);

    const validationError = validateFile(file);

    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);

    try {
      let mediaData: LocalMediaFile;

      if (file.type.startsWith("image/")) {
        mediaData = await getImageMetadata(file);
      } else if (file.type.startsWith("video/")) {
        mediaData = await getVideoMetadata(file);
      } else {
        throw new Error("Unsupported media type.");
      }

      onMediaSelect(mediaData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to process file.");
    } finally {
      setLoading(false);
    }
  };

  const handleFileInput = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];

    if (file) {
      processFile(file);
    }

    // Allows selecting the same file again.
    event.target.value = "";
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();

    if (disabled) {
      return;
    }

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
          "min-h-65 w-full rounded-2xl border-2 border-dashed flex items-center justify-center cursor-pointer transition-colors duration-200",
          isDragging
            ? "border-black bg-gray-100"
            : "border-gray-400 hover:border-gray-600",
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
          accept="image/*,video/*"
          onChange={handleFileInput}
          hidden
          disabled={disabled}
        />

        {loading ? (
          <div className="text-center">
            <p className="text-gray-600">Reading media...</p>
          </div>
        ) : (
          <div className="text-center">
            <div className="mb-3 text-4xl">+</div>

            <h3 className="mb-2 text-lg font-semibold text-gray-100">
              Drag n Drop your media here
            </h3>

            <p className="mb-3 text-sm text-gray-600">
              or <span className="underline">browse files</span>
            </p>

            <small className="text-sm text-gray-500">
              Images, GIFs & videos | Maximum 50 MB
            </small>
          </div>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
