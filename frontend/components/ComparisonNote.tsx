import type { ComparisonNoteData } from "@/lib/types";
import { DataState } from "@/components/DataState";

/**
 * The optional AI explanation of the (already-rendered) pitch mix table.
 * Wrapped in its own DataState so a Gemini failure, timeout, or malformed
 * response only degrades this panel — the numeric table above never
 * depends on this component succeeding.
 */
export function ComparisonNote({
  note,
  isLoading,
  error,
  onGenerate,
}: {
  note: ComparisonNoteData | null;
  isLoading: boolean;
  error: string | null;
  onGenerate: () => void;
}) {
  return (
    <aside className="panel brief-panel comparison-note" aria-labelledby="comparison-note-title">
      <div className="panel-heading brief-heading">
        <div>
          <p className="section-kicker section-kicker--ai">AI interpretation</p>
          <h2 id="comparison-note-title">AI Game Note</h2>
        </div>
        <button
          className="secondary-button"
          disabled={isLoading}
          onClick={onGenerate}
          type="button"
        >
          {isLoading ? "Generating…" : note ? "Regenerate" : "Generate AI Note"}
        </button>
      </div>

      {error ? (
        <DataState kind="error" onRetry={onGenerate}>
          {error}
        </DataState>
      ) : isLoading ? (
        <DataState kind="loading">Asking Gemini to explain the table above…</DataState>
      ) : !note ? (
        <DataState>Generate a note to see an AI explanation of the table above.</DataState>
      ) : (
        <div className="brief-sections">
          <section className="brief-section" data-kind="analysis">
            <div className="brief-section__index">01</div>
            <div>
              <h3>Summary</h3>
              <p>{note.summary}</p>
            </div>
          </section>

          {note.notableChanges.length > 0 ? (
            <section className="brief-section" data-kind="analysis">
              <div className="brief-section__index">02</div>
              <div>
                <h3>Notable Changes</h3>
                <ul className="brief-list">
                  {note.notableChanges.map((change) => (
                    <li key={change.metric}>{change.description}</li>
                  ))}
                </ul>
              </div>
            </section>
          ) : null}

          <section className="brief-section" data-kind="limitation">
            <div className="brief-section__index">
              {String(note.notableChanges.length > 0 ? 3 : 2).padStart(2, "0")}
            </div>
            <div>
              <h3>Sample Note</h3>
              <p>{note.sampleNote}</p>
            </div>
          </section>
        </div>
      )}
    </aside>
  );
}
