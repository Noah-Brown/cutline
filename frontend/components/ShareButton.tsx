"use client";

import { useState } from "react";
import { shareOrCopy, type ShareOutcome } from "@/lib/share";

type Props = { text: string };

type ButtonState = "idle" | ShareOutcome;

export function ShareButton({ text }: Props) {
  const [state, setState] = useState<ButtonState>("idle");

  const handle = async () => {
    const outcome = await shareOrCopy(text);
    setState(outcome);
    window.setTimeout(() => setState("idle"), 2000);
  };

  const label =
    state === "shared"
      ? "Shared!"
      : state === "copied"
        ? "Copied!"
        : state === "error"
          ? "Share failed"
          : "Share score";

  return (
    <button
      type="button"
      onClick={handle}
      className="rounded-full bg-navy-100 px-6 py-2 text-sm font-bold text-navy-900 shadow transition hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
    >
      {label}
    </button>
  );
}
