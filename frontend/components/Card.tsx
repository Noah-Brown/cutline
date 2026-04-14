"use client";

import { useState, type CSSProperties } from "react";
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

// Color = ground truth (green = qualifier, red = imposter).
// The ✓/✕ badge indicates whether the player's call was right.
function revealTint(result: ResultKind | undefined): string {
  switch (result) {
    case "correct":
    case "wrong_reject":
      return "bg-emerald-500/40";
    case "correct_reject":
    case "false_positive":
      return "bg-red-500/40";
    case "unanswered":
      return "bg-navy-900/50";
    default:
      return "bg-black/20";
  }
}

function revealBorder(result: ResultKind | undefined): string {
  switch (result) {
    case "correct":
    case "wrong_reject":
      return "border-emerald-400";
    case "correct_reject":
    case "false_positive":
      return "border-red-400";
    case "unanswered":
      return "border-navy-500/50";
    default:
      return "border-navy-500/60";
  }
}

function revealBadge(
  result: ResultKind | undefined,
): { symbol: string; className: string } | null {
  switch (result) {
    case "correct":
    case "correct_reject":
      return { symbol: "✓", className: "text-emerald-200" };
    case "false_positive":
    case "wrong_reject":
      return { symbol: "✕", className: "text-red-200" };
    default:
      return null;
  }
}

function revealAnimation(result: ResultKind | undefined): string {
  switch (result) {
    case "correct":
    case "correct_reject":
      return "animate-reveal-right";
    case "false_positive":
    case "wrong_reject":
      return "animate-reveal-wrong";
    default:
      return "animate-reveal";
  }
}

function playTint(mark: Mark | undefined): string {
  switch (mark) {
    case "yes":
      return "bg-emerald-500/55";
    case "no":
      return "bg-red-500/55";
    default:
      // Subtle darkening over the photo for consistent contrast with the name bar.
      return "bg-black/25";
  }
}

function playBorder(mark: Mark | undefined): string {
  switch (mark) {
    case "yes":
      return "border-emerald-300";
    case "no":
      return "border-red-300";
    default:
      return "border-navy-500/50";
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

function PlayerBackground({
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
        className="absolute inset-0 h-full w-full object-cover object-top"
      />
    );
  }

  return (
    <div
      aria-hidden
      className="absolute inset-0 flex items-center justify-center bg-navy-900/90"
    >
      <span className="text-2xl font-bold uppercase tracking-wider text-navy-100/80 sm:text-3xl">
        {initialsFor(name)}
      </span>
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
    "group relative aspect-square overflow-hidden rounded-xl border-2 shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-100";

  const nameBar = (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/50 to-transparent px-2 pb-1.5 pt-7">
      <span className="block text-center text-[11px] font-bold leading-tight text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)] sm:text-xs">
        {name}
      </span>
    </div>
  );

  if (mode === "reveal") {
    const tint = revealTint(result);
    const border = revealBorder(result);
    const badge = revealBadge(result);
    const animClass = revealAnimation(result);
    return (
      <button
        type="button"
        onClick={() => setShowExplanation((v) => !v)}
        style={
          {
            "--reveal-delay": revealDelayMs ? `${revealDelayMs}ms` : "0ms",
          } as CSSProperties
        }
        className={`${animClass} ${baseClasses} ${border}`}
        aria-label={`${name}: ${result ?? ""}`}
      >
        <PlayerBackground name={name} photoUrl={photoUrl} />
        <div className={`pointer-events-none absolute inset-0 ${tint}`} />
        {badge ? (
          <span
            className={`absolute right-1.5 top-1.5 text-xl font-black leading-none drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)] ${badge.className}`}
            aria-hidden
          >
            {badge.symbol}
          </span>
        ) : null}
        {showExplanation && explanation ? (
          <div className="absolute inset-0 flex items-center justify-center bg-black/80 px-2 text-center">
            <span className="text-[11px] font-normal leading-snug text-navy-50">
              {explanation}
            </span>
          </div>
        ) : (
          nameBar
        )}
      </button>
    );
  }

  const interactive = !disabled && onCycle;
  const tint = playTint(mark);
  const border = playBorder(mark);
  const disabledCls = disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer";
  const pressedState: "true" | "false" | "mixed" =
    mark === "yes" ? "true" : mark === "no" ? "false" : "mixed";
  const popCls = mark === "yes" || mark === "no" ? "animate-pop" : "";

  return (
    <button
      type="button"
      aria-pressed={pressedState}
      aria-label={`${name} — ${mark ?? "unmarked"}`}
      disabled={!interactive}
      onClick={onCycle}
      className={`${baseClasses} ${border} ${popCls} ${disabledCls}`}
    >
      <PlayerBackground name={name} photoUrl={photoUrl} />
      <div className={`pointer-events-none absolute inset-0 ${tint}`} />
      {mark && mark !== "blank" ? (
        <span
          className="absolute right-1.5 top-1.5 text-xl font-black leading-none text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]"
          aria-hidden
        >
          {markBadge(mark)}
        </span>
      ) : null}
      {nameBar}
    </button>
  );
}
