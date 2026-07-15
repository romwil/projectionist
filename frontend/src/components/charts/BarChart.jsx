/**
 * Horizontal bar chart rendered as pure SVG.
 *
 * @param {{ data: {label:string, value:number}[], accent?: string, barHeight?: number, gap?: number }} props
 */
export default function BarChart({ data = [], accent = "var(--accent)", barHeight = 24, gap = 6 }) {
  if (!data.length) return null;
  const maxVal = Math.max(...data.map((d) => d.value), 1);
  const labelWidth = 90;
  const valueWidth = 48;
  const chartLeft = labelWidth + 8;
  const chartRight = valueWidth + 8;
  const totalHeight = data.length * (barHeight + gap) - gap;

  return (
    <svg
      className="dash-bar-chart"
      viewBox={`0 0 400 ${totalHeight}`}
      preserveAspectRatio="xMinYMin meet"
      role="img"
      aria-label="Bar chart"
      width="100%"
    >
      {data.map((d, i) => {
        const y = i * (barHeight + gap);
        const barMaxWidth = 400 - chartLeft - chartRight;
        const barWidth = Math.max((d.value / maxVal) * barMaxWidth, 2);
        return (
          <g key={d.label}>
            <text
              x={labelWidth}
              y={y + barHeight / 2}
              textAnchor="end"
              dominantBaseline="central"
              fill="var(--muted)"
              fontSize="11"
              fontFamily="var(--font-body)"
            >
              {d.label.length > 14 ? d.label.slice(0, 13) + "…" : d.label}
            </text>
            <rect
              x={chartLeft}
              y={y + 2}
              width={barWidth}
              height={barHeight - 4}
              rx={4}
              fill={accent}
              opacity={0.85}
            />
            <text
              x={chartLeft + barWidth + 6}
              y={y + barHeight / 2}
              dominantBaseline="central"
              fill="var(--text)"
              fontSize="11"
              fontWeight="600"
              fontFamily="var(--font-body)"
            >
              {d.value.toLocaleString()}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
