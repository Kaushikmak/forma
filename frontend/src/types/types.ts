export type JobStatus =
  | "idle"
  | "validating"
  | "uploading"
  | "queued"
  | "processing"
  | "done"
  | "error";

export type LegoPalette = "classic";

export type StyleId = "lego";

export interface LegoParams {
  style: StyleId;
  width: number;
  palette: LegoPalette;
}

export type MediaType = "image" | "video" | "gif";

export interface LocalMediaFile {
  file: File;
  previewUrl: string;
  type: MediaType;
  sizeBytes: number;
  width: number;
  height: number;
  durationSec?: number;
}

export interface RemoteAsset {
  assetId: string;
  expiresAt: number;
}

export interface JobState {
  jobId: string | null;
  status: JobStatus;
  uploadProgress: number;
  renderProgress: number;
  resultUrl: string | null;
  errorMessage: string | null;
}
