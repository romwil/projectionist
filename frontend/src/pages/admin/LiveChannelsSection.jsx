import { useState } from "react";
import { getLiveChannelsStatus, refillLiveChannelsChannel } from "../../api/client";
import { buildCraftFiltersPayload, craftDraftFromStation } from "../../lib/liveChannelsCraft.js";
import { ownerLiveText } from "../../lib/liveChannelsOwnerCopy.js";
import LiveChannelsAdvanced from "./LiveChannelsAdvanced";
import LiveChannelsStudio from "./LiveChannelsStudio";

export { buildCraftFiltersPayload, craftDraftFromStation };
export { LiveJobRail, LiveReadyBadge, LiveStatusCheck, isLiveChannelsLaunched } from "./LiveChannelsParts.jsx";

/**
 * Admin → Live Channels. A native studio for the owner flow (turn on, create a
 * channel, go on air, seasonal shelves) with the connection/health plumbing
 * tucked into Setup → Advanced. ConfigPage owns the shared state (status
 * polling, publish jobs); this wrapper only owns the open channel-settings draft.
 */
export default function LiveChannelsSection(props) {
  const {
    liveChannelsStatus,
    setLiveChannelsStatus,
    stationSettingsOpen,
    setStationSettingsOpen,
    setLiveChannelsTab,
    setLiveBusy,
    setActionFeedback,
  } = props;
  const [stationCraftDraft, setStationCraftDraft] = useState(null);

  function openStationSettings(channelId) {
    if (stationSettingsOpen === channelId) {
      setStationSettingsOpen(null);
      setStationCraftDraft(null);
      return;
    }
    const row =
      (liveChannelsStatus?.channels || []).find((c) => (c.id || c.channel_id) === channelId) || {
        id: channelId,
      };
    setStationCraftDraft(craftDraftFromStation(row));
    setStationSettingsOpen(channelId);
    setLiveChannelsTab("stations");
  }

  async function refillStation(channelId, name) {
    if (!channelId) return;
    if (!window.confirm(`Rebuild the lineup for ${name || "this channel"}?`)) return;
    setLiveBusy(`refill-${channelId}`);
    try {
      const result = await refillLiveChannelsChannel(channelId);
      setActionFeedback(
        "live-channels",
        result.ok ? "success" : "error",
        ownerLiveText(result.note) || "Lineup rebuilt.",
        { block: "stations" },
      );
      setLiveChannelsStatus(await getLiveChannelsStatus());
    } catch (error) {
      setActionFeedback("live-channels", "error", ownerLiveText(error.message), { block: "stations" });
    } finally {
      setLiveBusy(null);
    }
  }

  const advancedProps = { ...props, stationCraftDraft, setStationCraftDraft, refillStation };

  return (
    <LiveChannelsStudio
      {...props}
      openStationSettings={openStationSettings}
      refillStation={refillStation}
      stationSettings={<LiveChannelsAdvanced {...advancedProps} panel="station" />}
      advancedSetup={<LiveChannelsAdvanced {...advancedProps} panel="setup" />}
    />
  );
}
