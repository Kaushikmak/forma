import { Request, Response } from "express";
import { StyleMetadata } from "../types/contract.js";

export const STYLES: Record<string, StyleMetadata> = {
  lego: {
    name: "LEGO Mosaic",
    description: "Convert images, animated GIFs, and videos into realistic LEGO stud brick mosaics.",
    schema: {
      type: "object",
      properties: {
        style: { type: "string", enum: ["lego"], default: "lego" },
        width: { type: "integer", minimum: 16, maximum: 256, default: 64 },
        tileSize: { type: "integer", enum: [8, 12, 16, 24, 32], default: 16 },
        palette: {
          type: "string",
          enum: [
            "classic",
            "extended",
            "monochrome",
            "pastel",
            "crayon",
            "earth",
            "cool",
            "warm",
          ],
          default: "classic",
        },
        quality: { type: "string", enum: ["standard", "high", "maximum"], default: "high" },
        fps: { type: "string", enum: ["original", "24", "30", "60"], default: "original" },
        bitrateMbps: { type: "number", minimum: 0.5, maximum: 20.0 },
      },
      required: ["style", "width", "palette"],
    },
  },
  ascii: {
    name: "ASCII Mosaic",
    description: "Convert images, animated GIFs, and videos into colored ASCII tile mosaics with custom color palettes.",
    schema: {
      type: "object",
      properties: {
        style: { type: "string", enum: ["ascii"], default: "ascii" },
        width: { type: "integer", minimum: 16, maximum: 256, default: 64 },
        tileSize: { type: "integer", enum: [8, 12, 16, 24, 32], default: 16 },
        palette: {
          type: "string",
          enum: [
            "mild",
            "vibrant",
            "dark",
            "matrix",
            "amber",
            "cyberpunk",
            "monochrome",
            "retro",
            "pastel",
            "nord",
            "gameboy",
            "classic",
            "extended",
            "crayon",
            "earth",
            "cool",
            "warm",
          ],
          default: "mild",
        },
        ramp: {
          type: "string",
          enum: ["default", "classic", "dense", "blocks", "simple"],
          default: "default",
        },
        quality: { type: "string", enum: ["standard", "high", "maximum"], default: "high" },
        fps: { type: "string", enum: ["original", "24", "30", "60"], default: "original" },
        strength: { type: "number", minimum: 0.0, maximum: 1.0, default: 0.5 },
        bitrateMbps: { type: "number", minimum: 0.5, maximum: 20.0 },
      },
      required: ["style", "width", "palette"],
    },
  },
};

export function getStyles(_req: Request, res: Response) {
  res.json(STYLES);
}
