import type { ReactNode } from "react";

/** A bordered table whose cells wrap long text instead of cutting it off. */
export function Table({ headers, children }: { headers: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full text-sm">
        <thead className="bg-panel text-left">
          <tr>
            {headers.map((header) => (
              <th key={header} className="px-3 py-2 text-[11px] font-medium tracking-wide whitespace-nowrap text-faint uppercase">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}

export function Cell({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`px-3 py-2 align-top break-words ${className}`}>{children}</td>;
}
