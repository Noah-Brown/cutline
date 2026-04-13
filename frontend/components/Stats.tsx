"use client";

import { useEffect, useState } from "react";
import { computeDisplayStats, type DisplayStats } from "@/lib/stats";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Highlight the player's score for this puzzle in the histogram. */
  highlightScore?: number | null;
};

export function Stats({ open, onClose, highlightScore = null }: Props) {
  const [stats, setStats] = useState<DisplayStats | null>(null);

  useEffect(() => {
    if (!open) return;
    setStats(computeDisplayStats());
  }, [open]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-20 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-2xl bg-navy-700 p-5 text-sm shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold uppercase tracking-[0.2em] text-navy-100/80">
            Statistics
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close stats"
            className="text-navy-100/60 hover:text-navy-100"
          >
            ✕
          </button>
        </div>

        {stats ? (
          <>
            <div className="mt-4 grid grid-cols-4 gap-2 text-center">
              <Stat value={stats.gamesPlayed} label="Played" />
              <Stat
                value={`${Math.round(stats.perfectRate * 100)}%`}
                label="Perfect"
              />
              <Stat value={stats.currentStreak} label="Current" />
              <Stat value={stats.maxStreak} label="Max" />
            </div>

            <h3 className="mt-5 text-xs font-bold uppercase tracking-[0.2em] text-navy-100/70">
              Score Distribution
            </h3>
            <Histogram
              data={stats.scoreDistribution}
              highlightScore={highlightScore}
            />
          </>
        ) : (
          <p className="mt-4 text-navy-100/60">Loading…</p>
        )}
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: number | string; label: string }) {
  return (
    <div>
      <p className="text-2xl font-black leading-none">{value}</p>
      <p className="mt-1 text-[10px] uppercase tracking-widest text-navy-100/60">
        {label}
      </p>
    </div>
  );
}

function Histogram({
  data,
  highlightScore,
}: {
  data: Array<{ score: number; count: number }>;
  highlightScore: number | null;
}) {
  if (data.length === 0) {
    return (
      <p className="mt-3 text-navy-100/60">
        Play a puzzle to start your distribution.
      </p>
    );
  }
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <ul className="mt-2 flex flex-col gap-1">
      {data.map(({ score, count }) => {
        const pct = Math.max(6, (count / max) * 100);
        const isHighlight = highlightScore === score;
        return (
          <li key={score} className="flex items-center gap-2">
            <span className="w-8 text-right font-mono text-xs tabular-nums text-navy-100/80">
              {score}
            </span>
            <div className="h-5 flex-1 overflow-hidden rounded bg-navy-900/40">
              <div
                className={`flex h-full items-center justify-end pr-2 text-[11px] font-bold text-navy-900 ${
                  isHighlight ? "bg-emerald-400" : "bg-navy-100"
                }`}
                style={{ width: `${pct}%` }}
              >
                {count}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
