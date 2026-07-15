/**
 * Horizontal progress bar — CSS-based, no SVG.
 *
 * @param {{ value: number, label?: string, detail?: string, color?: string }} props
 */
export default function ProgressBar({ value = 0, label, detail, color = "var(--accent)" }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="dash-progress" aria-label={label ? `${label}: ${clamped}%` : undefined}>
      {label ? (
        <div className="dash-progress-header">
          <span className="dash-progress-label">{label}</span>
          <span className="dash-progress-pct">{Math.round(clamped)}%</span>
        </div>
      ) : null}
      <div className="dash-progress-track">
        <div
          className="dash-progress-fill"
          style={{ width: `${clamped}%`, background: color }}
        />
      </div>
      {detail ? <span className="dash-progress-detail">{detail}</span> : null}
    </div>
  );
}
