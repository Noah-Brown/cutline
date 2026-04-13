"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchToday,
  submitSelections,
  type PuzzleResponse,
  type SubmitResponse,
} from "@/lib/api";
import {
  getSessionId,
  hasSubmitted,
  loadResults,
  loadSelections,
  markSubmitted,
  saveSelections,
} from "@/lib/session";
import { Grid } from "@/components/Grid";
import { Header } from "@/components/Header";
import { Reveal } from "@/components/Reveal";
import { recordSubmission } from "@/lib/stats";

const INSTRUCTION_KEY = "cutline_instructions_seen";

export default function HomePage() {
  const [puzzle, setPuzzle] = useState<PuzzleResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SubmitResponse | null>(null);
  const [showInstructions, setShowInstructions] = useState(false);

  // Load today's puzzle + restore local state.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await fetchToday();
        if (cancelled) return;
        setPuzzle(p);

        if (hasSubmitted(p.date)) {
          const cached = loadResults(p.date);
          if (cached) setResult(cached);
        } else {
          const prev = loadSelections(p.date);
          if (prev.length) setSelected(new Set(prev));
        }

        if (!window.localStorage.getItem(INSTRUCTION_KEY)) {
          setShowInstructions(true);
        }
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : "Failed to load puzzle";
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = useCallback(
    (pos: number) => {
      if (!puzzle) return;
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(pos)) next.delete(pos);
        else next.add(pos);
        saveSelections(puzzle.date, Array.from(next).sort((a, b) => a - b));
        return next;
      });
    },
    [puzzle],
  );

  const handleSubmit = useCallback(async () => {
    if (!puzzle || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await submitSelections({
        puzzleId: puzzle.puzzle_id,
        sessionId: getSessionId(),
        selections: Array.from(selected).sort((a, b) => a - b),
      });
      setResult(response);
      markSubmitted(puzzle.date, response);
      recordSubmission({
        puzzleDate: puzzle.date,
        score: response.score,
        perfect: response.perfect,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Submit failed";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }, [puzzle, selected, submitting]);

  const dismissInstructions = () => {
    window.localStorage.setItem(INSTRUCTION_KEY, "1");
    setShowInstructions(false);
  };

  const canSubmit = selected.size > 0 && !submitting;

  const content = useMemo(() => {
    if (loading) {
      return (
        <p className="mt-10 text-center text-sm text-navy-100/70">Loading…</p>
      );
    }
    if (error) {
      return (
        <div className="mt-10 rounded-lg border border-red-400/40 bg-red-500/10 p-4 text-center text-sm text-red-100">
          {error}
        </div>
      );
    }
    if (!puzzle) {
      return (
        <p className="mt-10 text-center text-sm text-navy-100/70">
          No puzzle available.
        </p>
      );
    }
    if (result) {
      return <Reveal response={result} category={puzzle.category} />;
    }

    return (
      <section className="flex flex-col gap-5">
        <div className="rounded-xl border border-navy-500/40 bg-navy-700/40 px-4 py-3 text-center">
          <p className="text-xs uppercase tracking-[0.2em] text-navy-100/60">
            Category
          </p>
          <p className="mt-1 text-xl font-bold sm:text-2xl">{puzzle.category}</p>
        </div>

        <Grid
          players={puzzle.players}
          selected={selected}
          onToggle={toggle}
          disabled={submitting}
        />

        <div className="flex flex-col items-center gap-2">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="rounded-full bg-navy-100 px-8 py-3 text-sm font-bold text-navy-900 shadow transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit"}
          </button>
          <p className="text-xs text-navy-100/60">
            {selected.size === 0
              ? "Tap the players you believe qualify."
              : `${selected.size} selected`}
          </p>
        </div>
      </section>
    );
  }, [loading, error, puzzle, result, selected, submitting, toggle, handleSubmit, canSubmit]);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col px-4 pb-10">
      {puzzle ? (
        <Header puzzleNumber={puzzle.puzzle_number} date={puzzle.date} />
      ) : (
        <div className="h-[88px]" />
      )}

      {content}

      {showInstructions ? (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/60 p-4">
          <div className="max-w-sm rounded-2xl bg-navy-700 p-5 text-sm shadow-xl">
            <h2 className="mb-2 text-base font-bold">How to play</h2>
            <p className="text-navy-100/90">
              You see one category and 9 player names. Tap the ones you think
              really qualify. <span className="font-semibold">A few are imposters</span>
              {" "}— you won't know how many.
            </p>
            <p className="mt-3 text-navy-100/90">
              +1 for each correct tap. −1 for each imposter you pick. −1 for
              each real qualifier you miss.
            </p>
            <button
              type="button"
              onClick={dismissInstructions}
              className="mt-4 w-full rounded-full bg-navy-100 px-4 py-2 text-sm font-bold text-navy-900"
            >
              Got it
            </button>
          </div>
        </div>
      ) : null}
    </main>
  );
}
