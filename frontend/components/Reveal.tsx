"use client";

import { useEffect, useState } from "react";
import type { PlayerResult, SubmitResponse } from "@/lib/api";
import { Card } from "./Card";
import { ShareButton } from "./ShareButton";
import { timeUntilNextPuzzle } from "@/lib/share";

type RevealProps = {
  response: SubmitResponse;
  category: string;
};

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
              selected={r.was_selected}
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
        <ShareButton text={share_text} />
        <p className="text-xs text-navy-100/60">
          Next puzzle in <span className="font-mono">{countdown}</span>
        </p>
      </div>

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
                <p className="font-semibold">{r.name}</p>
                <p className="text-navy-100/70">{r.explanation}</p>
              </div>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}

function emojiFor(result: PlayerResult["result"]): string {
  switch (result) {
    case "correct":
    case "correct_avoid":
      return "🟩";
    case "false_positive":
      return "🔴";
    case "missed":
      return "🟨";
  }
}
