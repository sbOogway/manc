// The report markdown and the headline links carry text from RSS feeds, so anything that
// reaches the DOM from them goes through a sanitiser first.
import DOMPurify from "dompurify";
import { marked } from "marked";

/** Markdown to HTML with every script, handler and non-http(s) URL removed. */
export function renderMarkdown(markdown: string): string {
  if (!markdown) return "";
  return DOMPurify.sanitize(marked.parse(markdown) as string, { USE_PROFILES: { html: true } });
}

/** A feed URL as an href, or nothing when its scheme is not http(s). */
export function safeHref(url: string): string | undefined {
  let parsed: URL;
  try {
    parsed = new URL(url.trim());
  } catch {
    return undefined;
  }
  return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : undefined;
}
