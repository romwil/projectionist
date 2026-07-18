import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getLibraryPage, listLibraryPages } from "../api/client";
import AppShell from "../layouts/AppShell";
import BackLink from "../components/BackLink";
import MessageText from "../components/MessageText";
import TitleCard from "../components/TitleCard";
import { ROUTES } from "../lib/backNav";

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

  if (pageId) {
    const blocks = page?.content?.blocks || [];
    return (
      <AppShell className="app-root explore-page" title={page?.name || "Saved response"} actions={<BackLink fallbackTo={ROUTES.library} />}>
        <main className="explore-main">
          <section className="explore-section">
            <div className="section-heading"><p className="eyebrow">Saved curator library</p><h1>{page?.name || "Loading…"}</h1></div>
            {blocks.map((block, index) => block.type === "title_cards" ? (
              <div className="inline-cards" key={index}>{(block.items || []).map((item) => <TitleCard key={`${item.media_type}-${item.tmdb_id || item.tvdb_id || item.title}`} item={item} compact />)}</div>
            ) : <MessageText key={index} content={block.content || ""} markdown />)}
            {page ? <div className="bulk-confirm-actions">
              <a className="ghost" href={`/api/saved-library/${page.id}/export?format=markdown`}>Download Markdown</a>
              <a className="ghost" href={`/api/saved-library/${page.id}/export?format=json`}>Download JSON</a>
              <a className="ghost" href={`/api/saved-library/${page.id}/export?format=txt`}>Download TXT</a>
              <button onClick={() => navigate(`/?saved_library=${encodeURIComponent(page.id)}`)}>Chat from here</button>
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
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search saved responses" aria-label="Search saved responses" />
        {Object.entries(groupedByDate(pages)).map(([date, entries]) => <div key={date}><h2>{date}</h2>{entries.map((entry) => <Link className="thread-row" key={entry.id} to={`/library/${entry.id}`}><strong>{entry.name}</strong><span>{entry.searchable_text.slice(0, 160)}</span></Link>)}</div>)}
      </section></main>
    </AppShell>
  );
}
