// Small line icons, drawn inline so they follow the text colour.

type IconProps = { className?: string };

function Svg({ className = "h-4 w-4", children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      {children}
    </svg>
  );
}

export const PlusIcon = (p: IconProps) => <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>;
export const MoonIcon = (p: IconProps) => <Svg {...p}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></Svg>;
export const SearchIcon = (p: IconProps) => <Svg {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Svg>;
export const ReturnIcon = (p: IconProps) => <Svg {...p}><path d="M20 4v7a4 4 0 0 1-4 4H4" /><path d="m8 11-4 4 4 4" /></Svg>;
export const BookIcon = (p: IconProps) => <Svg {...p}><path d="M4 19.5V5a2 2 0 0 1 2-2h14v16H6a2 2 0 0 0-2 2z" /><path d="M8 7h8" /></Svg>;
export const ChevronIcon = (p: IconProps) => <Svg {...p}><path d="m9 6 6 6-6 6" /></Svg>;

/** The brand mark: a knot of dots, a nod to threads being kept together. */
export function LogoMark({ className = "h-5 w-5" }: IconProps) {
  const dots = [[6, 5], [12, 3], [18, 5], [9, 11], [15, 11], [6, 17], [12, 19], [18, 17]];
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      {dots.map(([x, y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r={1.6} fill="currentColor" />)}
    </svg>
  );
}
