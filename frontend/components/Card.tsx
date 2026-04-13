"use client";

import { useState } from "react";
import { resolvePhotoUrl, type Mark, type ResultKind } from "@/lib/api";

type Mode = "play" | "reveal";

type CardProps = {
  name: string;
  photoUrl?: string | null;
  mark?: Mark;            // play mode: current tri-state
  disabled?: boolean;
  onCycle?: () => void;   // play mode: advance to next state
  mode?: Mode;
  result?: ResultKind;    // reveal mode
  explanation?: string;
  revealDelayMs?: number;
};

function revealColors(result: ResultKind | undefined): string {
  switch (result) {
    case "correct":
    case "correct_reject":
      return "bg-emerald-500/30 border-emerald-400 text-emerald-50";
    case "false_positive":
      return "bg-red-500/30 border-red-400 text-red-50";
    case "wrong_reject":
      return "bg-yellow-400/30 border-yellow-300 text-yellow-50";
    case "unanswered":
      return "bg-navy-700/50 border-navy-500/50 text-navy-100/80";
    default:
      return "bg-navy-700/60 border-navy-500/60 text-navy-50";
  }
}

function playColors(mark: Mark | undefined): string {
  switch (mark) {
    case "yes":
      return "bg-emerald-500/70 border-emerald-300 text-emerald-50 animate-pop";
    case "no":
      return "bg-red-500/70 border-red-300 text-red-50 animate-pop";
    default:
      return "bg-navy-700/70 border-navy-500/50 text-navy-50 hover:border-navy-100/70 hover:bg-navy-700";
  }
}

function markBadge(mark: Mark | undefined): string {
  if (mark === "yes") return "✓";
  if (mark === "no") return "✕";
  return "";
}

function initialsFor(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function PlayerAvatar({
  name,
  photoUrl,
}: {
  name: string;
  photoUrl: string | null | undefined;
}) {
  const [errored, setErrored] = useState(false);
  const resolved = resolvePhotoUrl(photoUrl);

  if (resolved && !errored) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={resolved}
        alt=""
        onError={() => setErrored(true)}
        className="h-10 w-10 rounded-full object-cover ring-1 ring-navy-100/30 sm:h-12 sm:w-12"
      />
    );
  }

  return (
    <div
      aria-hidden
      className="flex h-10 w-10 items-center justify-center rounded-full bg-navy-900/60 text-[11px] font-bold uppercase tracking-wider text-navy-100/80 ring-1 ring-navy-100/20 sm:h-12 sm:w-12 sm:text-xs"
    >
      {initialsFor(name)}
    </div>
  );
}

export function Card({
  name,
  photoUrl,
  mark,
  disabled,
  onCycle,
  mode = "play",
  result,
  explanation,
  revealDelayMs,
}: CardProps) {
  const [showExplanation, setShowExplanation] = useState(false);

  const baseClasses =
    "relative flex min-h-[108px] flex-col items-center justify-center gap-1 rounded-xl border-2 p-2 text-center text-xs font-semibold shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-100 sm:min-h-[128px] sm:text-sm";

  if (mode === "reveal") {
    const style = revealColors(result);
    return (
      <button
        type="button"
        onClick={() => setShowExplanation((v) => !v)}
        style={{ animationDelay: revealDelayMs ? `${revealDelayMs}ms` : undefined }}
        className={`animate-reveal ${baseClasses} ${style}`}
        aria-label={`${name}: ${result ?? ""}`}
      >
        <PlayerAvatar name={name} photoUrl={photoUrl} />
        <span className="leading-tight">{name}</span>
        {showExplanation && explanation ? (
          <span className="mt-1 text-[11px] font-normal leading-snug text-navy-50/90 sm:text-xs">
            {explanation}
          </span>
        ) : null}
      </button>
    );
  }

  const interactive = !disabled && onCycle;
  const style = playColors(mark);
  const disabledCls = disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer";
  const pressedState: "true" | "false" | "mixed" =
    mark === "yes" ? "true" : mark === "no" ? "false" : "mixed";

  return (
    <button
      type="button"
      aria-pressed={pressedState}
      aria-label={`${name} — ${mark ?? "unmarked"}`}
      disabled={!interactive}
      onClick={onCycle}
      className={`${baseClasses} ${style} ${disabledCls}`}
    >
      {mark && mark !== "blank" ? (
        <span
          className="absolute right-2 top-2 text-xs font-black"
          aria-hidden
        >
          {markBadge(mark)}
        </span>
      ) : null}
      <PlayerAvatar name={name} photoUrl={photoUrl} />
      <span className="leading-tight">{name}</span>
    </button>
  );
}
