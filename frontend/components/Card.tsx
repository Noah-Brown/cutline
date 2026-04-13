"use client";

import { useState } from "react";
import type { Mark, ResultKind } from "@/lib/api";

type Mode = "play" | "reveal";

type CardProps = {
  name: string;
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
      return "bg-emerald-500/30 border-emerald-400 text-emerald-50";
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

export function Card({
  name,
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
    "relative flex min-h-[88px] flex-col items-center justify-center rounded-xl border-2 p-2 text-center text-sm font-semibold shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-100 sm:min-h-[108px] sm:text-base";

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
      <span className="leading-tight">{name}</span>
    </button>
  );
}
