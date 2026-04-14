/** Copies the share text to the clipboard. Returns true on success. */
export async function copyShareText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the legacy path
  }

  if (typeof document !== "undefined") {
    try {
      const el = document.createElement("textarea");
      el.value = text;
      el.setAttribute("readonly", "");
      el.style.position = "fixed";
      el.style.opacity = "0";
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
      return true;
    } catch {
      return false;
    }
  }

  return false;
}

export type ShareOutcome = "shared" | "copied" | "cancelled" | "error";

/** Prefer the native share sheet (iOS/Android); fall back to clipboard. */
export async function shareOrCopy(text: string): Promise<ShareOutcome> {
  if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
    try {
      await navigator.share({ text });
      return "shared";
    } catch (err) {
      // User dismissed the share sheet — not an error.
      if (err instanceof DOMException && err.name === "AbortError") {
        return "cancelled";
      }
      // Anything else: fall through to clipboard.
    }
  }

  return (await copyShareText(text)) ? "copied" : "error";
}

/** Format the time remaining until the next puzzle (midnight ET). */
export function timeUntilNextPuzzle(now: Date = new Date()): string {
  // Compute midnight ET as a fixed UTC-4 offset (EDT). For EST you'd need
  // proper DST handling; the MVP approximates, which is adequate for a countdown.
  const nowUtcMs = now.getTime();
  const etNow = new Date(nowUtcMs - 4 * 60 * 60 * 1000);
  const nextEt = new Date(
    Date.UTC(
      etNow.getUTCFullYear(),
      etNow.getUTCMonth(),
      etNow.getUTCDate() + 1,
      0,
      0,
      0,
    ),
  );
  const nextUtcMs = nextEt.getTime() + 4 * 60 * 60 * 1000;
  const diffMs = Math.max(0, nextUtcMs - nowUtcMs);

  const h = Math.floor(diffMs / 3_600_000);
  const m = Math.floor((diffMs % 3_600_000) / 60_000);
  const s = Math.floor((diffMs % 60_000) / 1_000);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s
    .toString()
    .padStart(2, "0")}`;
}
