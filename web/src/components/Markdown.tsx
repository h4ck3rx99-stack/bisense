// Safe Markdown renderer for source text (clause text and tables). Raw HTML is never rendered:
// react-markdown ignores HTML unless a rehype-raw plugin is added, and we never add one.
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Fragment, type ReactNode } from "react";

const components: Components = {
  table: ({ children }) => (
    <div className="table-wrap">
      <table>{children}</table>
    </div>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  img: () => null,
};

export function Markdown({ text, className = "" }: { text: string; className?: string }) {
  return (
    <div className={`md ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} skipHtml>
        {text}
      </ReactMarkdown>
    </div>
  );
}

/** Plain text with a phrase highlighted (used for evidence snippets and quotes). */
export function Highlighted({ text, phrase }: { text: string; phrase?: string | null }): ReactNode {
  if (!phrase || phrase.length < 4) return text;
  const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ");
  const idx = norm(text).indexOf(norm(phrase).slice(0, 120));
  if (idx < 0) return text;
  // map normalised index back approximately (texts here are already single-spaced)
  const end = idx + Math.min(phrase.length, 120);
  return (
    <Fragment>
      {text.slice(0, idx)}
      <mark className="hl">{text.slice(idx, end)}</mark>
      {text.slice(end)}
    </Fragment>
  );
}
