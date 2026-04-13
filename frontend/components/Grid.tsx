"use client";

import type { PuzzlePlayer } from "@/lib/api";
import { Card } from "./Card";

type GridProps = {
  players: PuzzlePlayer[];
  selected: Set<number>;
  onToggle: (pos: number) => void;
  disabled?: boolean;
};

export function Grid({ players, selected, onToggle, disabled }: GridProps) {
  const byPos = new Map(players.map((p) => [p.grid_position, p]));
  return (
    <div className="grid grid-cols-3 gap-2 sm:gap-3">
      {Array.from({ length: 9 }, (_, pos) => {
        const p = byPos.get(pos);
        if (!p) return <div key={pos} />;
        return (
          <Card
            key={pos}
            name={p.name}
            selected={selected.has(pos)}
            disabled={disabled}
            onToggle={() => onToggle(pos)}
          />
        );
      })}
    </div>
  );
}
