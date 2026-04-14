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

/** Format the time remaining until the next puzzle (midnight US Central). */
export function timeUntilNextPuzzle(now: Date = new Date()): string {
  // Read the current moment as Chicago wall-clock components, then express
  // both "CT now" and "next CT midnight" as UTC-labeled Dates. Their
  // difference is the real-world ms until midnight CT and is correct across
  // DST transitions because Intl handles the offset for us.
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const p = Object.fromEntries(
    fmt
      .formatToParts(now)
      .filter((x) => x.type !== "literal")
      .map((x) => [x.type, x.value]),
  );

  const year = Number(p.year);
  const month = Number(p.month) - 1;
  const day = Number(p.day);
  // Some browsers emit "24" for midnight; normalize to 0.
  const hour = Number(p.hour) % 24;
  const ctNowAsUtc = Date.UTC(year, month, day, hour, Number(p.minute), Number(p.second));
  const nextMidnightAsUtc = Date.UTC(year, month, day + 1, 0, 0, 0);
  const diffMs = Math.max(0, nextMidnightAsUtc - ctNowAsUtc);

  const h = Math.floor(diffMs / 3_600_000);
  const m = Math.floor((diffMs % 3_600_000) / 60_000);
  const s = Math.floor((diffMs % 60_000) / 1_000);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s
    .toString()
    .padStart(2, "0")}`;
}
