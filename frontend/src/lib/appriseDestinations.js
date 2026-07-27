/**
 * Apprise destination helpers for Settings → Notifications.
 *
 * Backend still stores a newline-separated `apprise_urls` string; this module
 * parses that blob into row objects, masks secrets for display, and builds
 * URLs from curated popular schemes.
 */

/** @typedef {{ id: string, label: string, blurb: string }} AppriseSchemeOption */

/** Curated popular Apprise targets (plus paste-your-own). */
export const APPRISE_SCHEME_OPTIONS = /** @type {AppriseSchemeOption[]} */ ([
  {
    id: "discord",
    label: "Discord webhook",
    blurb: "Incoming webhook ID and token from a Discord channel.",
  },
  {
    id: "telegram",
    label: "Telegram",
    blurb: "Bot token from BotFather and a chat or channel id.",
  },
  {
    id: "slack",
    label: "Slack webhook",
    blurb: "Three path segments from a Slack Incoming Webhook URL.",
  },
  {
    id: "mailto",
    label: "Email (SMTP)",
    blurb: "Send via SMTP using Apprise’s mailto scheme.",
  },
  {
    id: "pushover",
    label: "Pushover",
    blurb: "User key and application API token.",
  },
  {
    id: "gotify",
    label: "Gotify",
    blurb: "Self-hosted Gotify hostname and application token.",
  },
  {
    id: "ntfy",
    label: "ntfy",
    blurb: "Topic on ntfy.sh or your own ntfy server.",
  },
  {
    id: "custom",
    label: "Paste your own",
    blurb: "Any Apprise URL — for advanced schemes not listed above.",
  },
]);

const SCHEME_LABELS = {
  discord: "Discord",
  tgram: "Telegram",
  telegram: "Telegram",
  slack: "Slack",
  mailto: "Email",
  mailtos: "Email",
  pover: "Pushover",
  pushover: "Pushover",
  gotify: "Gotify",
  gotifys: "Gotify",
  ntfy: "ntfy",
  ntfys: "ntfy",
};

/**
 * Split a stored Apprise URL blob the same way the backend does
 * (newlines / commas / semicolons; skip comments).
 * @param {string | null | undefined} raw
 * @returns {string[]}
 */
export function splitAppriseUrls(raw) {
  const text = String(raw || "").trim();
  if (!text) return [];
  const seen = new Set();
  const out = [];
  for (const line of text.replace(/[,;]/g, "\n").split("\n")) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith("#")) continue;
    for (const part of stripped.split(/[\s,;]+/)) {
      const url = part.trim();
      if (!url || url.startsWith("#") || seen.has(url)) continue;
      seen.add(url);
      out.push(url);
    }
  }
  return out;
}

/**
 * @param {string | null | undefined} raw
 * @returns {{ id: string, url: string }[]}
 */
export function parseAppriseDestinationRows(raw) {
  return splitAppriseUrls(raw).map((url, index) => ({
    id: `dest-${index}-${simpleHash(url)}`,
    url,
  }));
}

/**
 * @param {{ url: string }[] | string[]} rows
 * @returns {string}
 */
export function serializeAppriseDestinationRows(rows) {
  const urls = (Array.isArray(rows) ? rows : [])
    .map((row) => (typeof row === "string" ? row : row?.url))
    .map((url) => String(url || "").trim())
    .filter(Boolean);
  return [...new Set(urls)].join("\n");
}

/**
 * @param {string} url
 * @returns {string} scheme without trailing colon/slashes (lowercase)
 */
export function appriseSchemeOf(url) {
  const match = String(url || "").trim().match(/^([a-z][a-z0-9+.-]*):\/\//i);
  return match ? match[1].toLowerCase() : "";
}

/**
 * @param {string} url
 * @returns {string}
 */
export function appriseTypeLabel(url) {
  const scheme = appriseSchemeOf(url);
  if (!scheme) return "Custom";
  return SCHEME_LABELS[scheme] || scheme;
}

/**
 * Map a stored URL to a builder scheme id when we can parse fields back.
 * @param {string} url
 * @returns {string}
 */
export function detectBuilderScheme(url) {
  const scheme = appriseSchemeOf(url);
  if (scheme === "discord") return "discord";
  if (scheme === "tgram" || scheme === "telegram") return "telegram";
  if (scheme === "slack") return "slack";
  if (scheme === "mailto" || scheme === "mailtos") return "mailto";
  if (scheme === "pover" || scheme === "pushover") return "pushover";
  if (scheme === "gotify" || scheme === "gotifys") return "gotify";
  if (scheme === "ntfy" || scheme === "ntfys") return "ntfy";
  return "custom";
}

/**
 * Mask secrets in an Apprise URL for display (keep scheme + short tips).
 * @param {string} url
 * @returns {string}
 */
export function maskAppriseUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  const scheme = appriseSchemeOf(raw);
  if (!scheme) return maskToken(raw, 4, 2);

  const rest = raw.slice(scheme.length + 3); // after "scheme://"
  if (!rest) return `${scheme}://`;

  // mailto keeps host visible-ish but masks user/password
  if (scheme === "mailto" || scheme === "mailtos") {
    try {
      const parsed = new URL(raw);
      const user = parsed.username ? maskToken(decodeURIComponent(parsed.username), 2, 0) : "";
      const pass = parsed.password ? "••••" : "";
      const auth = user ? `${user}${pass ? `:${pass}` : ""}@` : "";
      const query = parsed.search || "";
      return `${scheme}://${auth}${parsed.host}${query}`;
    } catch {
      return `${scheme}://${maskPathSecrets(rest)}`;
    }
  }

  return `${scheme}://${maskPathSecrets(rest)}`;
}

/** Apprise path tokens are usually left literal (bot tokens contain `:`). */
function pathToken(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (/[\s<>"]/.test(text)) {
    throw new Error("Destination fields cannot contain spaces or angle brackets.");
  }
  return text;
}

/**
 * @param {string} schemeId
 * @param {Record<string, string>} fields
 * @returns {string}
 */
export function buildAppriseUrl(schemeId, fields = {}) {
  const f = Object.fromEntries(
    Object.entries(fields).map(([key, value]) => [key, String(value ?? "").trim()]),
  );

  switch (schemeId) {
    case "discord": {
      const id = pathToken(f.webhook_id);
      const token = pathToken(f.webhook_token);
      if (!id || !token) throw new Error("Discord needs a webhook ID and token.");
      return `discord://${id}/${token}/`;
    }
    case "telegram": {
      const token = pathToken(f.bot_token);
      const chat = pathToken(f.chat_id);
      if (!token || !chat) throw new Error("Telegram needs a bot token and chat id.");
      return `tgram://${token}/${chat}`;
    }
    case "slack": {
      const a = pathToken(f.token_a);
      const b = pathToken(f.token_b);
      const c = pathToken(f.token_c);
      if (!a || !b || !c) {
        throw new Error("Slack needs the three segments from your Incoming Webhook URL.");
      }
      return `slack://${a}/${b}/${c}/`;
    }
    case "mailto": {
      const user = pathToken(f.user);
      const password = pathToken(f.password);
      const host = pathToken(f.host);
      const to = String(f.to || "").trim();
      const port = f.port || "587";
      const useTls = f.use_tls !== "0" && f.use_tls !== "false";
      if (!user || !password || !host || !to) {
        throw new Error("Email needs SMTP user, password, host, and a To address.");
      }
      const scheme = useTls ? "mailtos" : "mailto";
      return `${scheme}://${encodeURIComponent(user)}:${encodeURIComponent(password)}@${host}:${port}?to=${encodeURIComponent(to)}`;
    }
    case "pushover": {
      const userKey = pathToken(f.user_key);
      const token = pathToken(f.api_token);
      if (!userKey || !token) throw new Error("Pushover needs a user key and API token.");
      return `pover://${userKey}@${token}`;
    }
    case "gotify": {
      const host = pathToken(f.host);
      const token = pathToken(f.token);
      const useTls = f.use_tls !== "0" && f.use_tls !== "false";
      if (!host || !token) throw new Error("Gotify needs a hostname and token.");
      const scheme = useTls ? "gotifys" : "gotify";
      const port = f.port ? `:${pathToken(f.port)}` : "";
      return `${scheme}://${host}${port}/${token}`;
    }
    case "ntfy": {
      const topic = pathToken(f.topic);
      if (!topic) throw new Error("ntfy needs a topic.");
      const host = pathToken(f.host);
      const useTls = f.use_tls !== "0" && f.use_tls !== "false";
      if (!host) return `ntfy://${topic}`;
      const scheme = useTls ? "ntfys" : "ntfy";
      return `${scheme}://${host}/${topic}`;
    }
    case "custom": {
      const url = f.url;
      if (!url) throw new Error("Paste an Apprise URL.");
      if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) {
        throw new Error("Apprise URLs look like scheme://… (for example discord://…).");
      }
      return url;
    }
    default:
      throw new Error("Unknown destination type.");
  }
}

/**
 * Best-effort parse of a URL back into builder fields.
 * @param {string} url
 * @returns {{ schemeId: string, fields: Record<string, string> }}
 */
export function parseAppriseUrlFields(url) {
  const raw = String(url || "").trim();
  const schemeId = detectBuilderScheme(raw);
  if (schemeId === "custom" || !raw) {
    return { schemeId: "custom", fields: { url: raw } };
  }

  try {
    if (schemeId === "discord") {
      const path = stripScheme(raw);
      const [webhookId = "", webhookToken = ""] = path.split("/").filter(Boolean);
      return {
        schemeId,
        fields: {
          webhook_id: decodeURIComponent(webhookId),
          webhook_token: decodeURIComponent(webhookToken),
        },
      };
    }
    if (schemeId === "telegram") {
      const path = stripScheme(raw);
      const [botToken = "", ...chatParts] = path.split("/").filter(Boolean);
      return {
        schemeId,
        fields: {
          bot_token: decodeURIComponent(botToken),
          chat_id: decodeURIComponent(chatParts.join("/")),
        },
      };
    }
    if (schemeId === "slack") {
      const parts = stripScheme(raw).split("/").filter(Boolean);
      return {
        schemeId,
        fields: {
          token_a: decodeURIComponent(parts[0] || ""),
          token_b: decodeURIComponent(parts[1] || ""),
          token_c: decodeURIComponent(parts[2] || ""),
        },
      };
    }
    if (schemeId === "mailto") {
      const parsed = new URL(raw);
      return {
        schemeId,
        fields: {
          user: decodeURIComponent(parsed.username || ""),
          password: decodeURIComponent(parsed.password || ""),
          host: parsed.hostname || "",
          port: parsed.port || (parsed.protocol === "mailtos:" ? "587" : "25"),
          to: parsed.searchParams.get("to") || "",
          use_tls: parsed.protocol === "mailtos:" ? "1" : "0",
        },
      };
    }
    if (schemeId === "pushover") {
      const body = stripScheme(raw);
      const at = body.indexOf("@");
      if (at === -1) return { schemeId: "custom", fields: { url: raw } };
      return {
        schemeId,
        fields: {
          user_key: decodeURIComponent(body.slice(0, at)),
          api_token: decodeURIComponent(body.slice(at + 1).replace(/\/$/, "")),
        },
      };
    }
    if (schemeId === "gotify") {
      const useTls = appriseSchemeOf(raw) === "gotifys";
      const body = stripScheme(raw);
      const slash = body.indexOf("/");
      const hostPort = slash === -1 ? body : body.slice(0, slash);
      const token = slash === -1 ? "" : body.slice(slash + 1).replace(/\/$/, "");
      const [host = "", port = ""] = hostPort.split(":");
      return {
        schemeId,
        fields: {
          host,
          port,
          token: decodeURIComponent(token),
          use_tls: useTls ? "1" : "0",
        },
      };
    }
    if (schemeId === "ntfy") {
      const useTls = appriseSchemeOf(raw) === "ntfys";
      const body = stripScheme(raw);
      const parts = body.split("/").filter(Boolean);
      if (parts.length === 1) {
        return { schemeId, fields: { topic: decodeURIComponent(parts[0]), host: "", use_tls: "1" } };
      }
      return {
        schemeId,
        fields: {
          host: parts[0] || "",
          topic: decodeURIComponent(parts.slice(1).join("/")),
          use_tls: useTls ? "1" : "0",
        },
      };
    }
  } catch {
    // fall through
  }
  return { schemeId: "custom", fields: { url: raw } };
}

/**
 * Field definitions for the destination builder form.
 * @param {string} schemeId
 * @returns {{ name: string, label: string, type?: string, placeholder?: string, required?: boolean, hint?: string }[]}
 */
export function builderFieldsFor(schemeId) {
  switch (schemeId) {
    case "discord":
      return [
        { name: "webhook_id", label: "Webhook ID", required: true, placeholder: "1234567890" },
        {
          name: "webhook_token",
          label: "Webhook token",
          required: true,
          type: "password",
          placeholder: "webhook token",
        },
      ];
    case "telegram":
      return [
        {
          name: "bot_token",
          label: "Bot token",
          required: true,
          type: "password",
          placeholder: "123456:ABC…",
        },
        { name: "chat_id", label: "Chat ID", required: true, placeholder: "-100…" },
      ];
    case "slack":
      return [
        {
          name: "token_a",
          label: "Token A (T…)",
          required: true,
          placeholder: "T00000000",
          hint: "From hooks.slack.com/services/A/B/C",
        },
        { name: "token_b", label: "Token B (B…)", required: true, placeholder: "B00000000" },
        {
          name: "token_c",
          label: "Token C",
          required: true,
          type: "password",
          placeholder: "XXXXXXXX",
        },
      ];
    case "mailto":
      return [
        { name: "user", label: "SMTP username", required: true },
        { name: "password", label: "SMTP password", required: true, type: "password" },
        { name: "host", label: "SMTP host", required: true, placeholder: "smtp.example.com" },
        { name: "port", label: "Port", placeholder: "587" },
        { name: "to", label: "To email", required: true, type: "email", placeholder: "you@example.com" },
        {
          name: "use_tls",
          label: "Use TLS (mailtos)",
          type: "checkbox",
          hint: "On for most providers (port 587).",
        },
      ];
    case "pushover":
      return [
        { name: "user_key", label: "User key", required: true, type: "password" },
        { name: "api_token", label: "Application API token", required: true, type: "password" },
      ];
    case "gotify":
      return [
        { name: "host", label: "Hostname", required: true, placeholder: "gotify.example.com" },
        { name: "port", label: "Port (optional)", placeholder: "443" },
        { name: "token", label: "Application token", required: true, type: "password" },
        { name: "use_tls", label: "Use HTTPS (gotifys)", type: "checkbox" },
      ];
    case "ntfy":
      return [
        { name: "topic", label: "Topic", required: true, placeholder: "projectionist-alerts" },
        {
          name: "host",
          label: "Server (optional)",
          placeholder: "ntfy.sh",
          hint: "Leave blank to use the public ntfy.sh topic URL.",
        },
        { name: "use_tls", label: "Use HTTPS (ntfys)", type: "checkbox" },
      ];
    case "custom":
    default:
      return [
        {
          name: "url",
          label: "Apprise URL",
          required: true,
          placeholder: "discord://webhook_id/webhook_token",
          hint: "One URL. See Apprise docs for every supported scheme.",
        },
      ];
  }
}

/** @param {string} schemeId */
export function defaultBuilderFields(schemeId) {
  const fields = {};
  for (const field of builderFieldsFor(schemeId)) {
    if (field.type === "checkbox") {
      fields[field.name] = "1";
    } else if (field.name === "port" && schemeId === "mailto") {
      fields[field.name] = "587";
    } else {
      fields[field.name] = "";
    }
  }
  return fields;
}

function stripScheme(url) {
  return String(url || "").replace(/^[a-z][a-z0-9+.-]*:\/\//i, "");
}

function maskPathSecrets(path) {
  return path
    .split("/")
    .map((segment) => {
      if (!segment) return segment;
      if (segment.includes("@")) {
        const at = segment.indexOf("@");
        return `${maskToken(segment.slice(0, at), 2, 0)}@${maskToken(segment.slice(at + 1), 2, 2)}`;
      }
      if (segment.includes("?")) {
        const [base, query = ""] = segment.split("?");
        return `${maskToken(base, 3, 2)}?${query
          .split("&")
          .map((pair) => {
            const [key, value = ""] = pair.split("=");
            if (/pass|token|key|secret/i.test(key)) return `${key}=••••`;
            return `${key}=${value}`;
          })
          .join("&")}`;
      }
      return maskToken(segment, 3, 2);
    })
    .join("/");
}

function maskToken(value, keepStart = 2, keepEnd = 2) {
  const text = String(value || "");
  if (text.length <= keepStart + keepEnd + 1) {
    return text ? "•".repeat(Math.min(text.length, 6)) : "";
  }
  return `${text.slice(0, keepStart)}…${text.slice(-keepEnd)}`;
}

function simpleHash(text) {
  let hash = 0;
  const str = String(text || "");
  for (let i = 0; i < str.length; i += 1) {
    hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
  }
  return hash.toString(36);
}
