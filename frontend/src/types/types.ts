export type JobStatus =
  | "idle"
  | "validating"
  | "uploading"
  | "queued"
  | "probing"
  | "processing"
  | "encoding"
  | "done"
  | "rejected"
  | "failed"
  | "cancelled"
  | "error";

export type LegoPalette =
  | "classic"
  | "extended"
  | "monochrome"
  | "pastel"
  | "crayon"
  | "earth"
  | "cool"
  | "warm";

export type AsciiPalette =
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
  | "gameboy";

export type LegoQuality = "standard" | "high" | "maximum";
export type LegoFps = "original" | "24" | "30" | "60";
export type StyleId = "lego" | "ascii";

export interface LegoParams {
  style: StyleId;
  width: number;
  tileSize: number;
  palette: LegoPalette | AsciiPalette;
  ramp?: string;
  strength?: number;
  quality: LegoQuality;
  fps: LegoFps;
  autoBitrate: boolean;
  bitrateMbps?: number; // 0.5 to 20.0 Mbps
}

export type MediaType = "image" | "video" | "gif";

export interface LocalMediaFile {
  file: File;
  previewUrl: string;
  type: MediaType;
  mimeType: string;
  sizeBytes: number;
  width: number;
  height: number;
  durationSec?: number;
  fps?: number;
}

export interface RemoteAsset {
  assetId: string;
  expiresAt: number;
}

export interface JobState {
  jobId: string | null;
  status: JobStatus;
  progress: number;
  resultUrl: string | null;
  errorMessage: string | null;
}
