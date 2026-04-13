// LocalStorage session and per-puzzle state.
// Keys:
//   session_id                   — anonymous UUID
//   puzzle_<date>_submitted      — boolean
//   puzzle_<date>_marks          — in-progress {yes:[], no:[]} state
//   puzzle_<date>_results        — cached SubmitResponse

import type { MarksPayload, SubmitResponse } from "./api";

const SESSION_KEY = "session_id";

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
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

const EMPTY_MARKS: MarksPayload = { yes: [], no: [] };

export function loadMarks(date: string): MarksPayload {
  if (typeof window === "undefined") return { ...EMPTY_MARKS };
  const raw = window.localStorage.getItem(`puzzle_${date}_marks`);
  if (!raw) return { ...EMPTY_MARKS };
  try {
    const parsed = JSON.parse(raw) as Partial<MarksPayload>;
    return {
      yes: Array.isArray(parsed.yes) ? parsed.yes : [],
      no: Array.isArray(parsed.no) ? parsed.no : [],
    };
  } catch {
    return { ...EMPTY_MARKS };
  }
}

export function saveMarks(date: string, marks: MarksPayload): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    `puzzle_${date}_marks`,
    JSON.stringify(marks),
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
