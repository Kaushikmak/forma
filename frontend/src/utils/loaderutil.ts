import type { JobState } from "../types/types";

export const getStageTitle = (status?: JobState["status"]) => {
  switch (status) {
    case "validating":
      return "Are you sure this is what you want to be doing?";
    case "uploading":
      return "Your file is leaving home. Please respect its privacy.";
    case "queued":
      return "You are not stuck. You are simply waiting in a queue.";
    case "probing":
      return "We are looking into things that probably shouldn't be looked into.";
    case "processing":
      return "Somewhere, a tiny underpaid worker in this server is questioning its career choices.";
    case "encoding":
      return "Turning your questionable decisions into a very large file.";
    case "done":
      return "It worked. Nobody knows why. Please don't touch anything.";
    case "rejected":
      return "The computer has reviewed your work and chosen violence.";
    case "failed":
      return "Well, that could have gone significantly better.";
    case "cancelled":
      return "You stopped it. The pixels will never know what happened.";
    case "error":
      return "Something went wrong. Probably nothing important. Probably.";
    default:
      return "Something is happening. This is generally how problems begin.";
  }
};

export const getStageDescription = (
  status?: JobState["status"],
  errorMessage?: string | null,
) => {
  switch (status) {
    case "uploading":
      return "transferring asset to server, don't worry it will autodelete :)";
    case "queued":
      return "waiting for underpaid workers to finish jobs";
    case "probing":
      return "inspecting your media, are you sure you didn't upload anything sus??";
    case "processing":
      return "hold on a minute, server gonna grab quick coffee";
    case "encoding":
      return "almost done I guess";
    case "done":
      return "YAY!! rendered successfully, can you give me star on github????";
    case "cancelled":
      return "Your cancelled T_T your fault";
    case "rejected":
    case "failed":
    case "error":
      return errorMessage ?? "An unexpected processing error occurred.";
    default:
      return "Please wait or not I don't really care";
  }
};
