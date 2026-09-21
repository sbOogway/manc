// @vitest-environment jsdom
// jsdom, not happy-dom: DOMPurify misreads happy-dom's tree (drops headings, keeps scripts)
import { expect, test } from "vitest";

import { renderMarkdown, safeHref } from "../lib/markdown";

test("renderMarkdown turns markdown into html", () => {
  const html = renderMarkdown("## Drivers\n\nA **hot** CPI print and a [link](https://x.test/a).");
  expect(html).toContain("<h2>Drivers</h2>");
  expect(html).toContain("<strong>hot</strong>");
  expect(html).toContain('<a href="https://x.test/a">link</a>');
});

test("renderMarkdown strips scripts, event handlers and javascript: links from feed text", () => {
  const hostile = [
    "## Headlines",
    "",
    "- <script>alert(1)</script>Fed holds",
    '- <img src=x onerror="alert(1)"> Gold up',
    "- [click](javascript:alert(1))",
    '- <a href="https://ok.test" onclick="alert(1)">fine</a>',
  ].join("\n");
  const html = renderMarkdown(hostile);
  expect(html).not.toContain("<script");
  expect(html).not.toContain("onerror");
  expect(html).not.toContain("onclick");
  expect(html).not.toContain("javascript:");
  expect(html).toContain("Fed holds");
  expect(html).toContain("Gold up");
  expect(html).toContain('<a href="https://ok.test">fine</a>');
});

test("renderMarkdown of nothing is nothing", () => {
  expect(renderMarkdown("")).toBe("");
});

test("safeHref keeps http(s) links and drops every other scheme", () => {
  expect(safeHref("https://www.reuters.com/markets/a-story")).toBe("https://www.reuters.com/markets/a-story");
  expect(safeHref("http://feed.test/x?y=1#z")).toBe("http://feed.test/x?y=1#z");
  expect(safeHref(" HTTPS://upper.test/ ")).toBe("https://upper.test/");
  expect(safeHref("javascript:alert(1)")).toBeUndefined();
  expect(safeHref("JavaScript:alert(1)")).toBeUndefined();
  expect(safeHref("data:text/html,<script>alert(1)</script>")).toBeUndefined();
  expect(safeHref("vbscript:x")).toBeUndefined();
  expect(safeHref("//protocol.relative/x")).toBeUndefined();
  expect(safeHref("not a url")).toBeUndefined();
  expect(safeHref("")).toBeUndefined();
});
