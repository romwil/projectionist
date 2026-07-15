/**
 * Simple donut chart rendered as pure SVG arcs.
 *
 * @param {{ segments: {label:string, value:number, color?:string}[], size?: number, thickness?: number }} props
 */
export default function DonutChart({ segments = [], size = 140, thickness = 22 }) {
  const total = segments.reduce((s, d) => s + d.value, 0);
  if (!total) return null;

  const cx = size / 2;
  const cy = size / 2;
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;

  const palette = [
    "var(--accent)",
    "color-mix(in srgb, var(--accent) 55%, var(--surface-2))",
    "var(--muted)",
    "color-mix(in srgb, var(--accent) 30%, var(--surface-2))",
  ];

  let cumulativeOffset = 0;

  return (
    <div className="dash-donut-wrap">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width={size}
        height={size}
        role="img"
        aria-label="Donut chart"
      >
        {segments.map((seg, i) => {
          const fraction = seg.value / total;
          const dashLength = fraction * circumference;
          const dashGap = circumference - dashLength;
          const offset = -cumulativeOffset;
          cumulativeOffset += dashLength;
          return (
            <circle
              key={seg.label}
              cx={cx}
              cy={cy}
              r={radius}
              fill="none"
              stroke={seg.color || palette[i % palette.length]}
              strokeWidth={thickness}
              strokeDasharray={`${dashLength} ${dashGap}`}
              strokeDashoffset={offset}
              transform={`rotate(-90 ${cx} ${cy})`}
            />
          );
        })}
      </svg>
      <ul className="dash-donut-legend">
        {segments.map((seg, i) => (
          <li key={seg.label}>
            <span
              className="dash-donut-swatch"
              style={{ background: seg.color || palette[i % palette.length] }}
            />
            <span className="dash-donut-legend-label">{seg.label}</span>
            <span className="dash-donut-legend-value">{seg.value.toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
