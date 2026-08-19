/**
 * Locked glass door chrome for /login, /join, and first-run /setup.
 * Atmosphere is CSS-only (CSP-safe, no extra tracking).
 */
export default function GlassDoor({
  eyebrow = "Projectionist",
  title,
  lede,
  children,
  footer,
  testId = "glass-door",
  halt = false,
}) {
  return (
    <div className={`glass-door${halt ? " glass-door--halt" : ""}`} data-testid={testId}>
      <div className="glass-door-atmosphere" aria-hidden="true">
        <div className="glass-door-grain" />
        <div className="glass-door-wash" />
      </div>
      <div className="glass-door-card">
        <p className="eyebrow glass-door-eyebrow">{eyebrow}</p>
        {title ? <h1 className="glass-door-title">{title}</h1> : null}
        {lede ? <p className="login-lede glass-door-lede">{lede}</p> : null}
        {children}
        {footer ? <div className="glass-door-footer">{footer}</div> : null}
      </div>
    </div>
  );
}
