import crypto from "crypto";
import { Request, Response } from "express";
import { DatabaseService } from "../services/db.js";
import { StorageService } from "../services/storage.js";

const MAX_UPLOAD_SIZE = 50 * 1024 * 1024; // 50 MiB Supabase storage plan ceiling

const ALLOWED_MIME_TYPES = new Set([
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

interface AssetMetadata {
  mimeType: string;
  fileSize: number;
  width?: number;
  height?: number;
  durationSec?: number;
  createdAt: number;
  expiresAt: number;
}

// In-memory fallback registry
export const assetSlots = new Map<string, AssetMetadata>();

export function createUploadController(storage: StorageService, db?: DatabaseService) {
  const uploadBucket = process.env.SUPABASE_UPLOAD_BUCKET || "upload";

  return {
    async requestUploadSlot(req: Request, res: Response) {
      const { fileSize, mimeType, width, height, durationSec } = req.body;

      if (typeof fileSize !== "number" || fileSize <= 0) {
        res.status(400).send("Invalid fileSize.");
        return;
      }

      if (fileSize > MAX_UPLOAD_SIZE) {
        res.status(413).send(`File size exceeds 50 MB limit (${(fileSize / (1024 * 1024)).toFixed(1)} MB).`);
        return;
      }

      if (!mimeType || !ALLOWED_MIME_TYPES.has(mimeType)) {
        res.status(415).send(`Unsupported media format: ${mimeType}`);
        return;
      }

      // Generate 128-bit asset ID
      const assetId = crypto.randomBytes(16).toString("hex");
      const now = Date.now();
      const expiresAt = now + 20 * 60 * 1000; // 20 minutes

      const slotRecord = {
        assetId,
        mimeType,
        fileSize,
        width,
        height,
        durationSec,
        createdAt: now,
        expiresAt,
      };

      assetSlots.set(assetId, slotRecord);
      if (db) {
        try {
          await db.saveUploadSlot(slotRecord);
        } catch (err) {
          console.warn("[UploadController] Failed to persist upload slot to DB:", err);
        }
      }

      let uploadUrl = `/api/uploads/${assetId}`;
      let slotExpiresAt = expiresAt;

      if (typeof storage.createSignedUploadUrl === "function") {
        try {
          const key = `uploads/${assetId}/input`;
          const signed = await storage.createSignedUploadUrl(uploadBucket, key);
          uploadUrl = signed.uploadUrl;
          slotExpiresAt = signed.expiresAt;
        } catch (err) {
          // Fall back to local PUT endpoint if minting fails
          console.warn("[UploadController] Falling back to local upload URL:", err);
          uploadUrl = `/api/uploads/${assetId}`;
        }
      }

      res.status(200).json({
        assetId,
        uploadUrl,
        expiresAt: slotExpiresAt,
      });
    },

    async handleDirectUpload(req: Request, res: Response) {
      const assetId = req.params.id;
      let metadata: AssetMetadata | undefined = assetSlots.get(assetId);

      if (!metadata && db) {
        const slot = await db.getUploadSlot(assetId);
        if (slot) {
          metadata = slot;
          assetSlots.set(assetId, slot);
        }
      }

      if (!metadata) {
        res.status(404).send("Upload slot not found or expired.");
        return;
      }

      if (Date.now() > metadata.expiresAt) {
        assetSlots.delete(assetId);
        res.status(410).send("Upload slot has expired.");
        return;
      }

      try {
        const key = `uploads/${assetId}/input`;
        await storage.save(uploadBucket, key, req, metadata.mimeType);
        res.status(200).send("Upload successful.");
      } catch (err) {
        res.status(500).send(err instanceof Error ? err.message : "Failed to store upload.");
      }
    },
  };
}
