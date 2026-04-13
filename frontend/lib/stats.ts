// Client-side aggregate stats, Wordle-style — persisted in localStorage.
//
// Streak rules:
//   • Any submission counts toward the streak (spec's open question:
//     playing = submitting). Perfects are tracked separately so the UI can
//     distinguish "games played" from "wins."
//   • A streak survives as long as you play on consecutive puzzle dates.
//     Missing a day resets currentStreak to 1 on your next play.
//   • When reading for display, we also check: if you haven't played today
//     *or* yesterday, currentStreak is shown as 0. The stored value stays
//     put; the display just reflects that the streak has lapsed.

const STATS_KEY = "cutline_stats_v1";

export type Stats = {
  gamesPlayed: number;
  perfectCount: number;
  currentStreak: number;
  maxStreak: number;
  lastPlayedDate: string | null; // YYYY-MM-DD
  scoreDistribution: Record<string, number>; // score → count
  recordedDates: string[]; // puzzle dates already counted (dedupe guard)
};

const EMPTY: Stats = {
  gamesPlayed: 0,
  perfectCount: 0,
  currentStreak: 0,
  maxStreak: 0,
  lastPlayedDate: null,
  scoreDistribution: {},
  recordedDates: [],
};

export function loadStats(): Stats {
  if (typeof window === "undefined") return { ...EMPTY };
  const raw = window.localStorage.getItem(STATS_KEY);
  if (!raw) return { ...EMPTY };
  try {
    const parsed = JSON.parse(raw) as Partial<Stats>;
    return {
      ...EMPTY,
      ...parsed,
      scoreDistribution: parsed.scoreDistribution ?? {},
      recordedDates: parsed.recordedDates ?? [],
    };
  } catch {
    return { ...EMPTY };
  }
}

function saveStats(stats: Stats): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STATS_KEY, JSON.stringify(stats));
}

function daysBetween(earlier: string, later: string): number {
  const a = new Date(earlier + "T00:00:00Z").getTime();
  const b = new Date(later + "T00:00:00Z").getTime();
  return Math.round((b - a) / 86_400_000);
}

/** Today in ET, as YYYY-MM-DD. Matches the backend's release schedule. */
export function todayEt(now: Date = new Date()): string {
  const etMs = now.getTime() - 4 * 60 * 60 * 1000; // EDT; see backend note
  const d = new Date(etMs);
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

/** Record one submission into the stats. Idempotent per puzzle date. */
export function recordSubmission(args: {
  puzzleDate: string;
  score: number;
  perfect: boolean;
}): Stats {
  const stats = loadStats();
  if (stats.recordedDates.includes(args.puzzleDate)) return stats;

  // Streak
  let currentStreak = stats.currentStreak;
  if (!stats.lastPlayedDate) {
    currentStreak = 1;
  } else {
    const gap = daysBetween(stats.lastPlayedDate, args.puzzleDate);
    if (gap === 1) currentStreak += 1;
    else if (gap > 1) currentStreak = 1;
    // gap === 0 shouldn't happen (blocked by recordedDates); gap < 0 (back-fill
    // of an earlier puzzle) leaves currentStreak unchanged.
  }

  const nextDistribution = { ...stats.scoreDistribution };
  const key = String(args.score);
  nextDistribution[key] = (nextDistribution[key] ?? 0) + 1;

  const next: Stats = {
    gamesPlayed: stats.gamesPlayed + 1,
    perfectCount: stats.perfectCount + (args.perfect ? 1 : 0),
    currentStreak,
    maxStreak: Math.max(stats.maxStreak, currentStreak),
    lastPlayedDate:
      !stats.lastPlayedDate || args.puzzleDate > stats.lastPlayedDate
        ? args.puzzleDate
        : stats.lastPlayedDate,
    scoreDistribution: nextDistribution,
    recordedDates: [...stats.recordedDates, args.puzzleDate],
  };
  saveStats(next);
  return next;
}

/** What to actually render — handles a lapsed current streak. */
export type DisplayStats = {
  gamesPlayed: number;
  perfectCount: number;
  perfectRate: number; // 0..1
  currentStreak: number; // 0 if lapsed
  maxStreak: number;
  scoreDistribution: Array<{ score: number; count: number }>; // sorted desc by score
  mostCommonScore: number | null;
};

export function computeDisplayStats(stats: Stats = loadStats()): DisplayStats {
  let currentStreak = stats.currentStreak;
  if (stats.lastPlayedDate) {
    const gap = daysBetween(stats.lastPlayedDate, todayEt());
    if (gap > 1) currentStreak = 0; // missed yesterday → streak is dead
  } else {
    currentStreak = 0;
  }

  const distribution = Object.entries(stats.scoreDistribution)
    .map(([score, count]) => ({ score: Number(score), count }))
    .sort((a, b) => b.score - a.score);

  const mostCommonScore =
    distribution.length === 0
      ? null
      : distribution.reduce((best, d) => (d.count > best.count ? d : best))
          .score;

  return {
    gamesPlayed: stats.gamesPlayed,
    perfectCount: stats.perfectCount,
    perfectRate: stats.gamesPlayed === 0 ? 0 : stats.perfectCount / stats.gamesPlayed,
    currentStreak,
    maxStreak: stats.maxStreak,
    scoreDistribution: distribution,
    mostCommonScore,
  };
}

/** Debug helper — wipes stats. Unused by app code; kept for the console. */
export function clearStats(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STATS_KEY);
}
