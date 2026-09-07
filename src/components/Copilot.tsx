import { useState } from "react";
import { ArrowUp, MessageSquare, X } from "lucide-react";
import type { CopilotResult, Alternate } from "../types";
import { api } from "../services/api";
const examples = [
  "Which flights are high risk?",
  "Which flights are affected by weather?",
  "Best alternate airport for Chennai?",
  "Which flights have downstream impact?",
  "Which routes intersect restricted airspace?",
];
export default function Copilot({
  onClose,
  onSelect,
  onAlternates,
}: {
  onClose: () => void;
  onSelect: (id: number) => void;
  onAlternates: (a: Alternate[]) => void;
}) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<CopilotResult>();
  const [asked, setAsked] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function ask(q: string) {
    if (q.trim().length < 3) return;
    setBusy(true);
    setError("");
    setAsked(q);
    try {
      const r = await api.ask(q);
      setResult(r);
      if (r.kind === "alternates") onAlternates(r.items as Alternate[]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <aside className="tool-panel panel copilot" aria-label="Operations copilot">
      <div className="panel-heading">
        <span>
          <MessageSquare size={14} /> OPERATIONS COPILOT
        </span>
        <button
          className="icon-button"
          aria-label="Close copilot"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </div>
      <div className="panel-scroll">
        <div className="tool-intro">
          <span className="eyebrow">ASK YOUR NETWORK</span>
          <h2>
            Operational questions.
            <br />
            Traceable answers.
          </h2>
          <p>
            Queries run against AeroPulse’s database and explainable analysis.
            No invented operational facts.
          </p>
        </div>
        <div className="query-examples">
          {examples.map((q) => (
            <button
              disabled={busy}
              key={q}
              onClick={() => {
                setQuestion(q);
                ask(q);
              }}
            >
              {q}
              <ArrowUp size={13} />
            </button>
          ))}
        </div>
        {asked && <div className="asked">{asked}</div>}
        {busy && (
          <p className="muted" role="status">
            Querying network data…
          </p>
        )}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        {result && !busy && (
          <div className="copilot-answer">
            <span className="eyebrow">DATABASE RESULT</span>
            <p>{result.answer}</p>
            {result.items.map((item, i) => (
              <div key={i} className="query-item">
                {item.flight_id ? (
                  <button onClick={() => onSelect(item.flight_id!)}>
                    <strong>{item.flight_number}</strong>
                    <span>{item.route_code}</span>
                    <b className={item.risk?.level.toLowerCase()}>
                      {item.risk?.score}
                    </b>
                  </button>
                ) : (
                  <>
                    <strong>{item.iata_code ?? item.route_code}</strong>
                    <span>{item.city ?? item.zone_name}</span>
                    {item.distance_km != null && (
                      <span>{Math.round(item.distance_km)} km</span>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      <form
        className="copilot-input"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <input
          aria-label="Operational question"
          placeholder="Ask an operational question…"
          value={question}
          maxLength={300}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button
          aria-label="Submit question"
          disabled={busy || question.trim().length < 3}
        >
          <ArrowUp size={18} />
        </button>
      </form>
      <div className="panel-foot">
        Rule-based intents · PostgreSQL / PostGIS
      </div>
    </aside>
  );
}
