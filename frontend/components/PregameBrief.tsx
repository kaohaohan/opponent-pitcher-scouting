import type { BriefSectionData } from "@/lib/types";
import { DataState } from "@/components/DataState";

type BriefBlock =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] };

function cleanMarkdownText(value: string): string {
  return value
    .replace(/^#{1,6}\s+/, "")
    .replace(/^\*+\s*/, "")
    .replace(/\*\*/g, "")
    .replace(/\*/g, "")
    .replace(/`/g, "")
    .trim();
}

function renderInlineMarkdown(value: string) {
  const parts = value.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return cleanMarkdownText(part);
  });
}

function parseBriefMarkdown(text: string): BriefBlock[] {
  const blocks: BriefBlock[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];

  function flushParagraph() {
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  }

  function flushList() {
    if (listItems.length > 0) {
      blocks.push({ kind: "list", items: listItems });
      listItems = [];
    }
  }

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || /^-{3,}$/.test(line)) {
      flushParagraph();
      flushList();
      continue;
    }

    if (/^#{1,6}\s+/.test(line)) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "heading", text: cleanMarkdownText(line) });
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      flushParagraph();
      listItems.push(line.replace(/^[-*]\s+/, "").trim());
      continue;
    }

    if (/^\*\*[^*]+:\*\*/.test(line) && line.length < 140) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "heading", text: cleanMarkdownText(line) });
      continue;
    }

    flushList();
    paragraph.push(line);
  }

  flushParagraph();
  flushList();

  return blocks;
}

function limitationItems(text: string): string[] {
  return text
    .split(/(?<=\.)\s+/)
    .map((item) => cleanMarkdownText(item))
    .filter(Boolean);
}

export function PregameBrief({
  sections,
  isLoading = false,
}: {
  sections: BriefSectionData[];
  isLoading?: boolean;
}) {
  return (
    <aside className="panel brief-panel" aria-labelledby="brief-title">
      <div className="panel-heading brief-heading">
        <div>
          <p className="section-kicker section-kicker--ai">Scouting interpretation</p>
          <h2 id="brief-title">Pre-game Brief</h2>
        </div>
      </div>

      <div className="brief-boundary">
        <p>
          Narrative interpretation of the structured facts shown at left. Statistics remain the
          source of truth.
        </p>
      </div>

      {isLoading ? (
        <DataState kind="loading">Asking Gemini to write the scouting brief…</DataState>
      ) : sections.length === 0 ? (
        <DataState>Generate a brief to see the backend analysis.</DataState>
      ) : (
        <div className="brief-sections">
          {sections.map((section, index) => (
            <section className="brief-section" data-kind={section.kind} key={section.title}>
              <div className="brief-section__index">{String(index + 1).padStart(2, "0")}</div>
              <div>
                <h3>{section.title}</h3>
                {section.kind === "limitation" ? (
                  <ul className="brief-list brief-list--limitations">
                    {limitationItems(section.text).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="brief-markdown">
                    {parseBriefMarkdown(section.text).map((block, blockIndex) => {
                      if (block.kind === "heading") {
                        return <h4 key={`${block.text}-${blockIndex}`}>{block.text}</h4>;
                      }
                      if (block.kind === "list") {
                        return (
                          <ul className="brief-list" key={`list-${blockIndex}`}>
                            {block.items.map((item) => (
                              <li key={item}>{renderInlineMarkdown(item)}</li>
                            ))}
                          </ul>
                        );
                      }
                      return (
                        <p key={`${block.text}-${blockIndex}`}>
                          {renderInlineMarkdown(block.text)}
                        </p>
                      );
                    })}
                  </div>
                )}
              </div>
            </section>
          ))}
        </div>
      )}
    </aside>
  );
}
