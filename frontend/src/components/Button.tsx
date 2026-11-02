import { forwardRef } from "react";

/**
 * VIS-003 — the shared button primitive: a plain neutral button by default,
 * with five explicit variants and three sizes (see DESIGN.md "Button & field
 * primitives"). New UI should reach for this instead of a bare `<button>`.
 *
 * Only one `variant="primary"` should exist per action group — that's the
 * single gold action a screen is steering someone toward.
 */
export type ButtonVariant = "neutral" | "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

type ButtonProps = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>;

const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "neutral", size = "md", className = "", type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`btn btn-${variant} btn-${size} ${className}`.trim()}
      {...rest}
    />
  );
});

export default Button;
