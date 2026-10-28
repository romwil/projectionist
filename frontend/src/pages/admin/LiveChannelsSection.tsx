import { useState } from "react";
import { useConfirmModal } from "../../hooks/useConfirmModal";
import useLiveChannelsAdmin, { type LiveChannelsAdminArgs } from "../../hooks/useLiveChannelsAdmin";
import { getLiveChannelsStatus, refillLiveChannelsChannel } from "../../api/client";
import { buildCraftFiltersPayload, craftDraftFromStation } from "../../lib/liveChannelsCraft.js";
import { ownerLiveText } from "../../lib/liveChannelsOwnerCopy.js";
import LiveChannelsAdvanced from "./LiveChannelsAdvanced";
import LiveChannelsStudio from "./LiveChannelsStudio";

export { buildCraftFiltersPayload, craftDraftFromStation };
export { LiveJobRail, LiveReadyBadge, LiveStatusCheck, isLiveChannelsLaunched } from "./LiveChannelsParts";

type SettingsBag = {
  tunarr?: Record<string, unknown>;
  features?: Record<string, unknown>;
  [key: string]: unknown;
};

type PersistSettings = (patch: Record<string, unknown>) => Promise<unknown> | unknown;

type LiveAdminShared = {
  settings?: SettingsBag;
  persistSettings?: PersistSettings;
  updateTunarrSettings?: (patch: Record<string, unknown>) => void;
  updateFeatureFlags?: (patch: Record<string, unknown>) => void;
  setSettings?: (next: unknown) => void;
} & Record<string, unknown>;

/**
 * Admin → Live Channels. Owns Live status, craft, publish, and engine jobs;
 * ConfigPage only passes shared settings helpers.
 */
export default function LiveChannelsSection(shared: LiveAdminShared) {
  const { confirm, modal } = useConfirmModal();
  const live = useLiveChannelsAdmin({
    settings: shared.settings,
    persistSettings: shared.persistSettings,
    updateTunarrSettings: shared.updateTunarrSettings,
    updateFeatureFlags: shared.updateFeatureFlags,
    setSettings: shared.setSettings as LiveChannelsAdminArgs["setSettings"],
    confirm,
  });
  const props = {
    ...shared,
    ...live,
    setActionFeedback: live.setActionFeedback,
    clearActionFeedback: live.clearActionFeedback,
  };
  const {
    liveChannelsStatus,
    setLiveChannelsStatus,
    stationSettingsOpen,
    setStationSettingsOpen,
    setLiveChannelsTab,
    setLiveBusy,
    setActionFeedback,
  } = props;
  const [stationCraftDraft, setStationCraftDraft] = useState<any | null>(null);

  function openStationSettings(channelId: any) {
    if (stationSettingsOpen === channelId) {
      setStationSettingsOpen(null);
      setStationCraftDraft(null);
      return;
    }
    const row =
      (liveChannelsStatus?.channels || []).find((c: any) => (c.id || c.channel_id) === channelId) || {
        id: channelId,
      };
    setStationCraftDraft(craftDraftFromStation(row));
    setStationSettingsOpen(channelId);
    setLiveChannelsTab("stations");
  }

  async function refillStation(channelId: any, name: any) {
    if (!channelId) return;
    if (
      !(await confirm({
        title: "Rebuild lineup",
        body: `Rebuild the lineup for ${name || "this channel"}?`,
        confirmLabel: "Rebuild",
      }))
    ) {
      return;
    }
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
    } catch (error: unknown) {
      setActionFeedback("live-channels", "error", ownerLiveText((error as { message?: string }).message), { block: "stations" });
    } finally {
      setLiveBusy(null);
    }
  }

  const advancedProps = { ...props, stationCraftDraft, setStationCraftDraft, refillStation };

  return (
    <>
      <LiveChannelsStudio
        {...props}
        openStationSettings={openStationSettings}
        refillStation={refillStation}
        stationSettings={<LiveChannelsAdvanced {...advancedProps} panel="station" />}
        advancedSetup={<LiveChannelsAdvanced {...advancedProps} panel="setup" />}
      />
      {modal}
    </>
  );
}
