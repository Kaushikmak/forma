import { Request, Response } from "express";
import path from "path";
import { StorageService } from "../services/storage.js";

const MIME_BY_EXT: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".mp4": "video/mp4",
};

export function createOutputController(storage: StorageService) {
  const resultsBucket = process.env.SUPABASE_RESULTS_BUCKET || "results";

  return {
    async getOutput(req: Request, res: Response) {
      const { jobId, filename } = req.params;
      const key = `outputs/${jobId}/${filename}`;

      let exists = await storage.exists(resultsBucket, key);
      let targetBucket = resultsBucket;
      if (!exists) {
        exists = await storage.exists("outputs", key);
        if (exists) targetBucket = "outputs";
      }

      if (!exists) {
        res.status(404).send("Result not found.");
        return;
      }

      const ext = path.extname(filename).toLowerCase();
      const contentType = MIME_BY_EXT[ext] || "application/octet-stream";

      res.setHeader("Content-Type", contentType);
      res.setHeader("Cache-Control", "public, max-age=86400, immutable");

      try {
        const stream = await storage.getStream(targetBucket, key);
        stream.pipe(res);
      } catch (err) {
        res.status(500).send(err instanceof Error ? err.message : "Error streaming result.");
      }
    },
  };
}
