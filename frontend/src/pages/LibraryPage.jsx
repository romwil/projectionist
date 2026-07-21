import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { deleteLibraryPage, getLibraryPage, listLibraryPages } from "../api/client";
import AppShell from "../layouts/AppShell";
import BackLink from "../components/BackLink";
import MessageText from "../components/MessageText";
import TitleCard from "../components/TitleCard";
import AgentAvatar from "../components/AgentAvatar";
import ShareActionMenu from "../components/ShareActionMenu";
import { ROUTES } from "../lib/backNav";
import { savedLibraryBlocks } from "../lib/savedLibraryBlocks";

function groupedByDate(pages) {
  return pages.reduce((groups, page) => {
    const date = new Date(page.created_at * 1000).toLocaleDateString();
    (groups[date] ||= []).push(page);
    return groups;
  }, {});
}

export default function LibraryPage() {
  const { pageId } = useParams();
  const navigate = useNavigate();
  const [pages, setPages] = useState([]);
  const [page, setPage] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (pageId) getLibraryPage(pageId).then(setPage);
    else listLibraryPages(query).then(setPages);
  }, [pageId, query]);
  useEffect(() => {
    if (pageId && new URLSearchParams(window.location.search).get("print") === "1" && page) window.print();
  }, [pageId, page]);

  async function archive(entry) {
    if (!window.confirm(`Archive "${entry.name}"?`)) return;
    await deleteLibraryPage(entry.id);
    setPages((current) => current.filter((item) => item.id !== entry.id));
  }

  if (pageId) {
    const blocks = page?.content?.blocks || [];
    return (
      <AppShell className="app-root explore-page" title={page?.name || "Saved response"} actions={<BackLink fallbackTo={ROUTES.library} />}>
        <main className="explore-main">
          <section className="explore-section">
            <div className="section-heading"><p className="eyebrow">Saved curator library</p><h1>{page?.name || "Loading…"}</h1></div>
            {savedLibraryBlocks(blocks).map((block, index) => {
              if (block.kind === "title_cards" || block.kind === "recommendations") {
                return <div className="inline-cards" key={index}>{block.items.map((item) => <TitleCard key={`${item.media_type}-${item.tmdb_id || item.tvdb_id || item.title}`} item={item} compact />)}</div>;
              }
              if (block.kind === "suggested_replies") {
                return (
                  <div className="suggested-replies" key={index} aria-label="Continue this saved conversation">
                    {block.replies.map((reply) => (
                      <button
                        type="button"
                        className="suggested-reply-chip"
                        key={reply}
                        onClick={() => navigate(`/?saved_library=${encodeURIComponent(page.id)}&follow_up=${encodeURIComponent(reply)}`)}
                      >
                        {reply}
                      </button>
                    ))}
                  </div>
                );
              }
              return <MessageText key={index} content={block.content} markdown />;
            })}
            {page ? <div className="library-detail-actions">
              <ShareActionMenu
                page={page}
                content={page.content}
                name={page.name}
                sourceSessionId={page.source_session_id}
                sourceMessageId={page.source_message_id}
                extraActions={[{ label: "Chat from here", icon: "forum", onClick: () => navigate(`/?saved_library=${encodeURIComponent(page.id)}`) }]}
              />
            </div> : null}
          </section>
        </main>
      </AppShell>
    );
  }
  return (
    <AppShell className="app-root explore-page" title="Library" actions={<BackLink fallbackTo={ROUTES.chat} />}>
      <main className="explore-main"><section className="explore-section">
        <div className="section-heading"><p className="eyebrow">Your saved curator responses</p><h1>Library</h1></div>
        <label className="library-search">
          <span className="material-symbols-outlined" aria-hidden="true">search</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search saved responses" aria-label="Search saved responses" />
        </label>
        {Object.entries(groupedByDate(pages)).map(([date, entries]) => <div key={date}><h2>{date}</h2>{entries.map((entry) => (
          <article className="thread-row library-row" key={entry.id}>
            <button type="button" className="library-row-main" onClick={() => navigate(`/library/${entry.id}`)}>
              <span className="library-row-title"><strong>{entry.name}</strong>{entry.persona?.name ? <span className="message-agent-meta library-persona-badge"><AgentAvatar name={entry.persona.name} /><span>{entry.persona.name}</span></span> : null}</span>
              <em>{entry.summary || entry.searchable_text.slice(0, 160)}</em>
            </button>
            <ShareActionMenu
              page={entry}
              content={entry.content}
              name={entry.name}
              sourceSessionId={entry.source_session_id}
              sourceMessageId={entry.source_message_id}
              extraActions={[
                { label: "Open", icon: "open_in_new", onClick: () => navigate(`/library/${entry.id}`) },
                { label: "Chat from here", icon: "forum", onClick: () => navigate(`/?saved_library=${encodeURIComponent(entry.id)}`) },
                { label: "Archive", icon: "archive", onClick: () => archive(entry) },
              ]}
            />
          </article>
        ))}</div>)}
      </section></main>
    </AppShell>
  );
}
