/**
 * Circular percentage gauge rendered as pure SVG.
 * Color shifts based on thresholds: green <30%, amber 30-60%, red >60%.
 *
 * @param {{ value: number, label?: string, size?: number, invert?: boolean }} props
 *   value  — percentage 0-100
 *   invert — when true, high values are good (green) instead of bad
 */
export default function Gauge({ value = 0, label, size = 110, invert = false }) {
  const clamped = Math.max(0, Math.min(100, value));
  const thickness = 10;
  const radius = (size - thickness) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * radius;
  const filled = (clamped / 100) * circumference;

  let color;
  if (invert) {
    color = clamped >= 60 ? "var(--success)" : clamped >= 30 ? "var(--accent)" : "var(--danger)";
  } else {
    color = clamped < 30 ? "var(--success)" : clamped < 60 ? "var(--accent)" : "var(--danger)";
  }

  return (
    <div className="dash-gauge" aria-label={label ? `${label}: ${clamped}%` : `${clamped}%`}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}>
        {/* Track */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke="var(--surface-2)"
          strokeWidth={thickness}
        />
        {/* Filled arc */}
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference - filled}`}
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{ transition: "stroke-dasharray 0.4s ease" }}
        />
        {/* Center text */}
        <text
          x={cx}
          y={cy}
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--text)"
          fontSize="22"
          fontWeight="700"
          fontFamily="var(--font-body)"
        >
          {Math.round(clamped)}%
        </text>
      </svg>
      {label ? <p className="dash-gauge-label">{label}</p> : null}
    </div>
  );
}
