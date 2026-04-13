export type PuzzlePlayer = {
  grid_position: number;
  name: string;
  player_id: number;
};

export type PuzzleResponse = {
  puzzle_id: number;
  puzzle_number: number;
  date: string; // YYYY-MM-DD
  category: string;
  players: PuzzlePlayer[];
};

export type ResultKind =
  | "correct"
  | "false_positive"
  | "missed"
  | "correct_avoid";

export type PlayerResult = {
  grid_position: number;
  player_id: number;
  name: string;
  is_qualifier: boolean;
  was_selected: boolean;
  result: ResultKind;
  explanation: string;
};

export type SubmitResponse = {
  puzzle_id: number;
  score: number;
  max_score: number;
  perfect: boolean;
  results: PlayerResult[];
  share_text: string;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {}
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export async function fetchToday(): Promise<PuzzleResponse> {
  const res = await fetch(`${API_BASE}/api/puzzle/today`, {
    cache: "no-store",
  });
  return handle<PuzzleResponse>(res);
}

export async function submitSelections(args: {
  puzzleId: number;
  sessionId: string;
  selections: number[];
}): Promise<SubmitResponse> {
  const res = await fetch(`${API_BASE}/api/puzzle/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      puzzle_id: args.puzzleId,
      session_id: args.sessionId,
      selections: args.selections,
    }),
  });
  return handle<SubmitResponse>(res);
}
