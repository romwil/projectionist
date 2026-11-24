/** Owner-facing sentence for a youth join. The title stays on this side of the request. */

export type RoomApproval = {
  id?: string;
  status?: string;
  requester_name?: string;
  ceiling?: string;
  title?: string;
  content_rating?: string;
  title_above?: boolean;
};

export function approvalSentence(row: RoomApproval): string {
  const name = String(row.requester_name || "Someone").trim() || "Someone";
  const ceiling = String(row.ceiling || "the youth limit").trim() || "the youth limit";
  const limit = `${name} wants to join. Approving limits this room to ${ceiling}.`;
  if (!row.title_above) return limit;
  const title = String(row.title || "").trim();
  const rating = String(row.content_rating || "").trim();
  const rated = title && rating
    ? `${title} is rated ${rating}.`
    : rating
      ? `This title is rated ${rating}.`
      : "This title is above that limit.";
  return `${limit} ${rated} Approving stops it.`;
}
