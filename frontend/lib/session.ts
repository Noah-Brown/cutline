// LocalStorage session and per-puzzle state.
// Keys per the design spec:
//   session_id                       — anonymous UUID
//   puzzle_<date>_submitted          — boolean
//   puzzle_<date>_selections         — in-progress selections (int[])
//   puzzle_<date>_results            — cached SubmitResponse
//   streak_current / streak_max      — maintained by /streak endpoint + locally

import type { SubmitResponse } from "./api";

const SESSION_KEY = "session_id";

function uuid(): string {
  // Prefer the native crypto.randomUUID when available (modern browsers).
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback — RFC 4122 v4-ish; good enough for anonymous session scoping.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function getSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  let id = window.localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = uuid();
    window.localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function loadSelections(date: string): number[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(`puzzle_${date}_selections`);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as number[]) : [];
  } catch {
    return [];
  }
}

export function saveSelections(date: string, selections: number[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    `puzzle_${date}_selections`,
    JSON.stringify(selections),
  );
}

export function markSubmitted(date: string, response: SubmitResponse): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(`puzzle_${date}_submitted`, "true");
  window.localStorage.setItem(
    `puzzle_${date}_results`,
    JSON.stringify(response),
  );
}

export function loadResults(date: string): SubmitResponse | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(`puzzle_${date}_results`);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SubmitResponse;
  } catch {
    return null;
  }
}

export function hasSubmitted(date: string): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(`puzzle_${date}_submitted`) === "true";
}
