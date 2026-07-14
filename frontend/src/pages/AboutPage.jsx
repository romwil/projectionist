import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHealth } from "../api/client";

const GITHUB_URL = "https://github.com/romwil/curatorx";
const DOCKER_HUB_URL = "https://hub.docker.com/r/romwil/curatorx";
const DOCS_URL = `${GITHUB_URL}/tree/main/docs`;

export default function AboutPage() {
  const [version, setVersion] = useState("");

  useEffect(() => {
    getHealth()
      .then((data) => setVersion(data?.version || ""))
      .catch(() => setVersion(""));
  }, []);

  return (
    <div className="editorial-page about-page" data-testid="about-page">
      <header className="editorial-header">
        <p className="eyebrow">CuratorX</p>
        <h1>About</h1>
        <p className="editorial-lede">
          A private cinema companion for your Plex and *arr stack — opinions in chat, taste in the
          library, credentials that stay home.
        </p>
        {version ? (
          <p className="editorial-meta" data-testid="about-version">
            Version {version}
          </p>
        ) : null}
      </header>

      <section className="editorial-section">
        <h2>The story</h2>
        <p>
          CuratorX grew out of living with a big personal library and wanting a curator who knew it —
          not another remote catalog that forgets where your files live. It indexes what you already
          own, learns from how you rate and refuse titles, and talks like the friend you want in the aisle.
        </p>
        <p>
          Owners configure the stack once. Household members sign in with Plex. Nobody has to pretend this
          is a SaaS marketing site.
        </p>
      </section>

      <section className="editorial-section">
        <h2>Links</h2>
        <ul className="editorial-links">
          <li>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">
              GitHub
            </a>
          </li>
          <li>
            <a href={DOCS_URL} target="_blank" rel="noreferrer">
              Documentation
            </a>
          </li>
          <li>
            <a href={DOCKER_HUB_URL} target="_blank" rel="noreferrer">
              Docker Hub · romwil/curatorx
            </a>
          </li>
          <li>
            <Link to="/privacy">Privacy &amp; data use</Link>
          </li>
          <li>
            <a href={`${GITHUB_URL}/blob/main/LICENSE`} target="_blank" rel="noreferrer">
              License · MIT
            </a>
          </li>
        </ul>
      </section>

      <p className="editorial-back">
        <Link to="/">Back to chat</Link>
        {" · "}
        <Link to="/settings">Settings</Link>
      </p>
    </div>
  );
}
