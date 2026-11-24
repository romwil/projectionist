import { useEffect, useState } from "react";
import { decideSessionApproval, listSessionApprovals } from "../../api/client";
import type { JsonObject } from "../../api/types";
import Button from "../../components/Button";
import SettingsPageHeader from "../../components/settings/SettingsPageHeader";
import SettingsPanel from "../../components/settings/SettingsPanel";
import { approvalSentence, type RoomApproval } from "../../lib/sessionApprovalCopy";

function asApproval(row: JsonObject): RoomApproval {
  return {
    id: String(row.id || ""),
    status: String(row.status || ""),
    requester_name: String(row.requester_name || ""),
    ceiling: String(row.ceiling || ""),
    title: String(row.title || ""),
    content_rating: String(row.content_rating || ""),
    title_above: Boolean(row.title_above),
  };
}

/** The owner answers a youth join here. Delivery of a push waits. */
export default function RoomApprovalsPage() {
  const [rows, setRows] = useState<RoomApproval[] | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");

  function load() {
    return listSessionApprovals()
      .then((data) => {
        setError("");
        const waiting = (data?.approvals || [])
          .map(asApproval)
          .filter((row) => row.status === "pending" && row.requester_name);
        setRows(waiting);
      })
      .catch(() => {
        setRows([]);
        setError("Could not load join requests.");
      });
  }

  useEffect(() => {
    void load();
  }, []);

  async function answer(id: string, decision: "approve" | "not_now") {
    setBusyId(id);
    setError("");
    try {
      await decideSessionApproval(id, decision);
      await load();
    } catch {
      setError("That request is not available.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <div className="settings-page" data-testid="room-approvals-page">
      <SettingsPageHeader title="Room approvals" testId="room-approvals-heading">
        Someone in Youth mode needs a yes before they join. Approving limits the room. Not now leaves the film as it is.
      </SettingsPageHeader>
      <SettingsPanel testId="room-approvals-list">
        {rows === null ? <p className="field-help">Loading…</p> : null}
        {error ? (
          <p className="field-help" role="alert" data-testid="room-approvals-error">
            {error}
          </p>
        ) : null}
        {rows && rows.length === 0 ? (
          <p className="field-help" data-testid="room-approvals-empty">
            No one is waiting to join.
          </p>
        ) : null}
        {rows?.map((row) => (
          <div key={row.id} data-testid={`room-approval-${row.id}`}>
            <p>{approvalSentence(row)}</p>
            <Button
              variant="primary"
              data-testid={`room-approval-approve-${row.id}`}
              disabled={busyId === row.id}
              onClick={() => void answer(String(row.id), "approve")}
            >
              Approve
            </Button>
            <Button
              data-testid={`room-approval-decline-${row.id}`}
              disabled={busyId === row.id}
              onClick={() => void answer(String(row.id), "not_now")}
            >
              Not now
            </Button>
          </div>
        ))}
      </SettingsPanel>
    </div>
  );
}
