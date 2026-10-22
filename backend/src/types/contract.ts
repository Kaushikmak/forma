export type JobStatus =
  | "queued"
  | "probing"
  | "processing"
  | "encoding"
  | "done"
  | "failed"
  | "rejected"
  | "cancelled"
  | "expired";

export type TerminalStatus = "done" | "failed" | "rejected" | "cancelled" | "expired";

export type ErrorCode =
  | "INPUT_MISSING"
  | "UNSUPPORTED_TYPE"
  | "UNREADABLE_MEDIA"
  | "DECODE_FAILED"
  | "TOO_LARGE"
  | "TOO_LARGE_PIXELS"
  | "TOO_MANY_FRAMES"
  | "TOO_LONG"
  | "UNKNOWN_STYLE"
  | "UNSUPPORTED_FOR_STYLE"
  | "INVALID_PARAMS"
  | "OUTPUT_TOO_LARGE"
  | "TIMEOUT"
  | "INTERNAL"
  | "MAX_ATTEMPTS"
  | "UNSUPPORTED_VERSION"
  | "EXPIRED"
  | "CANCELLED"
  | "QUOTA_EXCEEDED";

export interface LegoParams {
  style: "lego";
  width: number;
  tileSize?: number;
  palette:
    | "classic"
    | "extended"
    | "monochrome"
    | "pastel"
    | "crayon"
    | "earth"
    | "cool"
    | "warm";
  quality?: "standard" | "high" | "maximum";
  fps?: "original" | "24" | "30" | "60";
  bitrateMbps?: number;
}

export interface AsciiParams {
  style: "ascii";
  width: number;
  tileSize?: number;
  cellSize?: number;
  palette:
    | "mild"
    | "vibrant"
    | "dark"
    | "matrix"
    | "amber"
    | "cyberpunk"
    | "monochrome"
    | "retro"
    | "pastel"
    | "nord"
    | "gameboy"
    | "classic"
    | "extended"
    | "crayon"
    | "earth"
    | "cool"
    | "warm";
  ramp?: string;
  quality?: "standard" | "high" | "maximum";
  fps?: "original" | "24" | "30" | "60";
  strength?: number;
  contrast?: number;
  saturation?: number;
  gamma?: number;
  skipWhite?: number;
  autoLevels?: boolean;
  invert?: boolean;
  smooth?: number;
  writeTxt?: boolean;
  bitrateMbps?: number;
}

export interface JobLimits {
  maxBytes?: number;
  maxPixels?: number;
  maxFrames?: number;
  maxDurationSec?: number;
  maxFps?: number;
  maxOutputWidth?: number;
  timeoutSec?: number;
}

export interface JobEnvelope {
  v: 1;
  jobId: string;
  style: string;
  params: Record<string, unknown>;
  input: {
    bucket: string;
    key: string;
  };
  output: {
    bucket: string;
    prefix: string;
  };
  mediaKind?: "image" | "gif" | "video";
  deviceId?: string;
  limits?: JobLimits;
  createdAt: number;
  expiresAt: number;
}

export interface JobState {
  jobId: string;
  status: JobStatus;
  progress: number;
  updatedAt: number;
  attempts: number;
  cancel?: number;
  deviceId?: string;
  mediaKind?: "image" | "gif" | "video";
  inputWidth?: number;
  inputHeight?: number;
  resultBucket?: string;
  resultKey?: string;
  resultUrl?: string;
  contentType?: string;
  width?: number;
  height?: number;
  frames?: number;
  durationSec?: number;
  bytes?: number;
  cacheHit?: number;
  processingMs?: number;
  errorCode?: ErrorCode;
  errorMessage?: string;
  refundable?: number;
  refunded?: boolean;
}

export interface FinishedEvent {
  jobId: string;
  status: TerminalStatus;
  errorCode?: ErrorCode;
  refundable: 0 | 1;
}

export interface StyleMetadata {
  name: string;
  description: string;
  schema: Record<string, unknown>;
}
