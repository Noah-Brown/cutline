type HeaderProps = {
  puzzleNumber: number;
  date: string;
};

export function Header({ puzzleNumber, date }: HeaderProps) {
  const d = new Date(date + "T00:00:00");
  const pretty = d.toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <header className="flex flex-col items-center gap-1 pt-6 pb-4">
      <h1 className="text-3xl font-black tracking-tight text-navy-50">
        Cutline
      </h1>
      <p className="text-xs uppercase tracking-[0.2em] text-navy-100/70">
        #{puzzleNumber} · {pretty}
      </p>
    </header>
  );
}
