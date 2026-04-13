"use client";

import { useState } from "react";
import { copyShareText } from "@/lib/share";

type Props = { text: string };

export function ShareButton({ text }: Props) {
  const [state, setState] = useState<"idle" | "copied" | "error">("idle");

  const handle = async () => {
    const ok = await copyShareText(text);
    setState(ok ? "copied" : "error");
    window.setTimeout(() => setState("idle"), 2000);
  };

  return (
    <button
      type="button"
      onClick={handle}
      className="rounded-full bg-navy-100 px-6 py-2 text-sm font-bold text-navy-900 shadow transition hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
    >
      {state === "copied"
        ? "Copied!"
        : state === "error"
          ? "Copy failed"
          : "Share score"}
    </button>
  );
}
