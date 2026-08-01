import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildProgramHoverModel,
  formatProgramDisplayTitle,
  formatProgramEpisodeLabel,
  formatSeasonEpisodeCode,
  programDigInItem,
  programEpisodeTitle,
} from "./liveProgramDetail.js";

describe("liveProgramDetail helpers", () => {
  it("formats TV episode labels without inventing titles", () => {
    const ep = {
      title: "Gilligan's Island",
      episode_title: "The Big Gold Strike",
      season: 1,
      episode: 10,
      media_type: "show",
    };
    assert.equal(programEpisodeTitle(ep), "The Big Gold Strike");
    assert.equal(formatSeasonEpisodeCode(ep), "S1E10");
    assert.equal(formatProgramEpisodeLabel(ep), "S1E10 · The Big Gold Strike");
    assert.equal(
      formatProgramDisplayTitle(ep),
      "Gilligan's Island — S1E10 · The Big Gold Strike",
    );

    const bareShow = { title: "Gilligan's Island", media_type: "show" };
    assert.equal(programEpisodeTitle(bareShow), "");
    assert.equal(formatProgramEpisodeLabel(bareShow), "");
    assert.equal(formatProgramDisplayTitle(bareShow), "Gilligan's Island");
  });

  it("formats movies with year and soft-fails overview-less dig-in", () => {
    const movie = {
      title: "Heat",
      year: 1995,
      overview: "A crew of professionals.",
      media_type: "movie",
      plex_rating_key: "9001",
      content_rating: "R",
    };
    assert.equal(formatProgramDisplayTitle(movie), "Heat (1995)");
    const hover = buildProgramHoverModel(movie, { kind: "guide" });
    assert.equal(hover.title, "Heat");
    assert.equal(hover.subtitle, "1995");
    assert.equal(hover.overview, "A crew of professionals.");
    assert.equal(hover.digInItem.rating_key, "9001");
    assert.equal(hover.digInItem.media_type, "movie");

    assert.equal(programDigInItem({ title: "Heat", media_type: "movie" }), null);
  });

  it("digs TV into the show rating key, not the episode key", () => {
    const item = programDigInItem({
      title: "Homicide: Life on the Street",
      episode_title: "Hostage (1)",
      media_type: "show",
      plex_rating_key: "ep-55",
      show_plex_rating_key: "show-12",
    });
    assert.equal(item.media_type, "show");
    assert.equal(item.rating_key, "show-12");
  });

  it("builds Up next hover with episode richness", () => {
    const hover = buildProgramHoverModel(
      {
        title: "Gilligan's Island",
        episode_title: "The Big Gold Strike",
        season: 1,
        episode: 10,
        media_type: "show",
        content_rating: "TV-G",
        show_plex_rating_key: "105",
      },
      { kind: "next" },
    );
    assert.equal(hover.eyebrow, "Up next");
    assert.equal(hover.subtitle, "S1E10 · The Big Gold Strike");
    assert.ok(hover.digInItem);
  });
});
