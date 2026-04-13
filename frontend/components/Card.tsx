"use client";

import { useState } from "react";
import type { ResultKind } from "@/lib/api";

type Mode = "play" | "reveal";

type CardProps = {
  name: string;
  selected: boolean;
  disabled?: boolean;
  onToggle?: () => void;
  mode?: Mode;
  result?: ResultKind;
  explanation?: string;
  revealDelayMs?: number;
};

function colorsFor(result: ResultKind | undefined): string {
  switch (result) {
    case "correct":
      return "bg-emerald-500/25 border-emerald-400 text-emerald-50";
    case "correct_avoid":
      return "bg-emerald-500/15 border-emerald-500/40 text-emerald-100/80";
    case "false_positive":
      return "bg-red-500/30 border-red-400 text-red-50";
    case "missed":
      return "bg-yellow-400/25 border-yellow-300 text-yellow-50";
    default:
      return "bg-navy-700/60 border-navy-500/60 text-navy-50";
  }
}

export function Card({
  name,
  selected,
  disabled,
  onToggle,
  mode = "play",
  result,
  explanation,
  revealDelayMs,
}: CardProps) {
  const [showExplanation, setShowExplanation] = useState(false);

  if (mode === "reveal") {
    const style = colorsFor(result);
    return (
      <button
        type="button"
        onClick={() => setShowExplanation((v) => !v)}
        style={{ animationDelay: revealDelayMs ? `${revealDelayMs}ms` : undefined }}
        className={`animate-reveal relative flex min-h-[88px] flex-col items-center justify-center rounded-xl border-2 p-2 text-center text-sm font-semibold shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-100 sm:min-h-[108px] sm:text-base ${style}`}
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

  const interactive = !disabled && onToggle;
  const base =
    "relative flex min-h-[88px] items-center justify-center rounded-xl border-2 p-2 text-center text-sm font-semibold shadow-sm transition sm:min-h-[108px] sm:text-base";
  const state = selected
    ? "bg-navy-100 text-navy-900 border-navy-100 animate-pop"
    : "bg-navy-700/70 text-navy-50 border-navy-500/50 hover:border-navy-100/70 hover:bg-navy-700";
  const disabledCls = disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer";

  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={!interactive}
      onClick={onToggle}
      className={`${base} ${state} ${disabledCls} focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-100`}
    >
      <span className="leading-tight">{name}</span>
    </button>
  );
}
