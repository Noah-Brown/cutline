"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchByDate,
  fetchToday,
  submitMarks,
  type Mark,
  type MarksPayload,
  type PuzzleResponse,
  type SubmitResponse,
} from "@/lib/api";
import {
  getSessionId,
  hasSubmitted,
  loadMarks,
  loadResults,
  markSubmitted,
  saveMarks,
} from "@/lib/session";
import { Grid } from "@/components/Grid";
import { Header } from "@/components/Header";
import { Reveal } from "@/components/Reveal";
import { recordSubmission } from "@/lib/stats";

const INSTRUCTION_KEY = "cutline_instructions_seen_v3";

function nextMark(current: Mark): Mark {
  if (current === "blank") return "yes";
  if (current === "yes") return "no";
  return "blank";
}

function marksToPayload(marks: Map<number, Mark>): MarksPayload {
  const yes: number[] = [];
  const no: number[] = [];
  for (const [pos, mark] of marks.entries()) {
    if (mark === "yes") yes.push(pos);
    else if (mark === "no") no.push(pos);
  }
  return { yes: yes.sort((a, b) => a - b), no: no.sort((a, b) => a - b) };
}

function payloadToMarks(payload: MarksPayload): Map<number, Mark> {
  const map = new Map<number, Mark>();
  for (const p of payload.yes) map.set(p, "yes");
  for (const p of payload.no) map.set(p, "no");
  return map;
}

export default function HomePage() {
  const [puzzle, setPuzzle] = useState<PuzzleResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [marks, setMarks] = useState<Map<number, Mark>>(new Map());
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SubmitResponse | null>(null);
  const [showInstructions, setShowInstructions] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Optional ?date=YYYY-MM-DD preview: aim at the archive endpoint for QA
    // of upcoming puzzles without perturbing the "today" rollover logic.
    const previewDate =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("date")
        : null;
    (async () => {
      try {
        const p = previewDate ? await fetchByDate(previewDate) : await fetchToday();
        if (cancelled) return;
        setPuzzle(p);

        if (hasSubmitted(p.date)) {
          const cached = loadResults(p.date);
          if (cached) setResult(cached);
        } else {
          const prev = loadMarks(p.date);
          if (prev.yes.length + prev.no.length > 0) {
            setMarks(payloadToMarks(prev));
          }
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

  const cycle = useCallback(
    (pos: number) => {
      if (!puzzle) return;
      setMarks((prev) => {
        const next = new Map(prev);
        const current = next.get(pos) ?? "blank";
        const after = nextMark(current);
        if (after === "blank") next.delete(pos);
        else next.set(pos, after);
        saveMarks(puzzle.date, marksToPayload(next));
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
      const response = await submitMarks({
        puzzleId: puzzle.puzzle_id,
        sessionId: getSessionId(),
        marks: marksToPayload(marks),
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
  }, [puzzle, marks, submitting]);

  const dismissInstructions = () => {
    window.localStorage.setItem(INSTRUCTION_KEY, "1");
    setShowInstructions(false);
  };

  const markCount = marks.size;
  const totalCards = puzzle?.players.length ?? 9;
  const allMarked = markCount === totalCards;
  const canSubmit = allMarked && !submitting;

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
          marks={marks}
          onCycle={cycle}
          disabled={submitting}
        />

        <p className="text-center text-[11px] text-navy-100/60">
          Tap to cycle: blank → <span className="text-emerald-300">YES</span> →{" "}
          <span className="text-red-300">NO</span> → blank. Mark every card to
          submit.
        </p>

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
            {allMarked
              ? `All ${totalCards} marked · ready to submit`
              : `${markCount}/${totalCards} marked · mark every card to submit`}
          </p>
        </div>
      </section>
    );
  }, [loading, error, puzzle, result, marks, submitting, cycle, handleSubmit, canSubmit, markCount]);

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
              One category, nine names. Tap a card to cycle:
            </p>
            <ul className="mt-2 space-y-1 text-navy-100/90">
              <li>
                <span className="font-bold text-emerald-300">YES</span> — you
                think this name qualifies
              </li>
              <li>
                <span className="font-bold text-red-300">NO</span> — you think
                it's an imposter
              </li>
            </ul>
            <p className="mt-3 text-navy-100/90">
              Mark every card (YES or NO), then submit. +1 for each correct
              call, 0 for each wrong one. Max score: 9.
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
