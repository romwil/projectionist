type NewReplyChipProps = {
  visible?: boolean;
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
};

export default function NewReplyChip({ visible, onClick }: NewReplyChipProps) {
  if (!visible) return null;

  return (
    <button
      type="button"
      className="new-reply-chip"
      data-testid="new-reply-chip"
      onClick={onClick}
      aria-label="Scroll to new reply"
    >
      New reply ↓
    </button>
  );
}
