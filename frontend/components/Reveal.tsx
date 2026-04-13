"use client";

import { useEffect, useState } from "react";
import type { PlayerResult, ResultKind, SubmitResponse } from "@/lib/api";
import { Card } from "./Card";
import { ShareButton } from "./ShareButton";
import { Stats } from "./Stats";
import { timeUntilNextPuzzle } from "@/lib/share";

type RevealProps = {
  response: SubmitResponse;
  category: string;
};

function emojiFor(result: ResultKind): string {
  switch (result) {
    case "correct":
    case "correct_reject":
      return "🟩";
    case "false_positive":
      return "🔴";
    case "wrong_reject":
      return "🟨";
    case "unanswered":
      return "⬜";
  }
}

function labelFor(result: ResultKind): string {
  switch (result) {
    case "correct":
      return "Correct (yes)";
    case "correct_reject":
      return "Correct (imposter spotted)";
    case "false_positive":
      return "Missed — imposter";
    case "wrong_reject":
      return "Missed — real qualifier";
    case "unanswered":
      return "Unanswered";
  }
}

export function Reveal({ response, category }: RevealProps) {
  const { score, max_score, perfect, results, share_text } = response;

  const byPos = new Map<number, PlayerResult>(
    results.map((r) => [r.grid_position, r]),
  );

  const [countdown, setCountdown] = useState(() => timeUntilNextPuzzle());
  useEffect(() => {
    const id = window.setInterval(() => {
      setCountdown(timeUntilNextPuzzle());
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  const [statsOpen, setStatsOpen] = useState(false);

  return (
    <section className="flex flex-col gap-5">
      <div className="text-center">
        <p className="text-xs uppercase tracking-[0.2em] text-navy-100/60">
          {category}
        </p>
        <p className="mt-2 text-5xl font-black leading-none">
          {score}
          <span className="text-navy-100/60"> / {max_score}</span>
        </p>
        {perfect ? (
          <p className="mt-2 text-sm font-semibold uppercase tracking-widest text-emerald-300">
            Perfect
          </p>
        ) : null}
      </div>

      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {Array.from({ length: 9 }, (_, pos) => {
          const r = byPos.get(pos);
          if (!r) return <div key={pos} />;
          return (
            <Card
              key={pos}
              mode="reveal"
              name={r.name}
              photoUrl={r.photo_url}
              result={r.result}
              explanation={r.explanation}
              revealDelayMs={pos * 90}
            />
          );
        })}
      </div>

      <p className="text-center text-xs text-navy-100/50">
        Tap a card for the explanation.
      </p>

      <div className="flex flex-col items-center gap-3">
        <div className="flex items-center gap-3">
          <ShareButton text={share_text} />
          <button
            type="button"
            onClick={() => setStatsOpen(true)}
            className="rounded-full border border-navy-100/40 px-6 py-2 text-sm font-bold text-navy-50 transition hover:bg-navy-100/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
          >
            Stats
          </button>
        </div>
        <p className="text-xs text-navy-100/60">
          Next puzzle in <span className="font-mono">{countdown}</span>
        </p>
      </div>

      <Stats
        open={statsOpen}
        onClose={() => setStatsOpen(false)}
        highlightScore={score}
      />

      <details className="rounded-lg bg-navy-700/40 p-3 text-sm">
        <summary className="cursor-pointer text-navy-100/80">
          See full results
        </summary>
        <ul className="mt-2 flex flex-col gap-2">
          {results.map((r) => (
            <li key={r.grid_position} className="flex items-start gap-2">
              <span className="mt-0.5 text-base" aria-hidden>
                {emojiFor(r.result)}
              </span>
              <div>
                <p className="font-semibold">
                  {r.name}{" "}
                  <span className="text-xs font-normal text-navy-100/60">
                    · {labelFor(r.result)}
                  </span>
                </p>
                <p className="text-navy-100/70">{r.explanation}</p>
              </div>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
