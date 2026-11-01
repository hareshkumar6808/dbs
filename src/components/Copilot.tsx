import { FormEvent, useRef, useState } from "react";
import { ArrowUp, Bot, Database, MessageSquare, Sparkles, X } from "lucide-react";
import type { CopilotResult, Alternate } from "../types";
import { api } from "../services/api";

const examples = [
  "Which aircraft are within 200 km of MAA right now?",
  "Which flights are high risk and why?",
  "What active disruptions are affecting flights?",
  "Which routes intersect restricted airspace?",
];
type Exchange = { question: string; result?: CopilotResult; error?: string };

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
  const [history, setHistory] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const scroll = useRef<HTMLDivElement>(null);

  async function ask(raw: string) {
    const q = raw.trim();
    if (q.length < 3 || busy) return;
    setQuestion("");
    setPendingQuestion(q);
    setBusy(true);
    setHistory((items) => [...items, { question: q }]);
    try {
      const result = await api.ask(q);
      setHistory((items) => items.map((item, i) => i === items.length - 1 ? { ...item, result } : item));
      if (result.kind === "alternates") onAlternates(result.items as Alternate[]);
    } catch (error) {
      setHistory((items) => items.map((item, i) => i === items.length - 1 ? { ...item, error: (error as Error).message } : item));
    } finally {
      setBusy(false);
      setPendingQuestion("");
      requestAnimationFrame(() => scroll.current?.scrollTo({ top: scroll.current.scrollHeight, behavior: "smooth" }));
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(question);
  }

  return (
    <section className="tool-panel panel copilot copilot-workspace" aria-label="Operations copilot">
      <header className="workspace-tool-header">
        <div className="workspace-tool-title">
          <span className="tool-icon"><Bot size={20} /></span>
          <div>
            <span className="eyebrow">AEROPULSE INTELLIGENCE</span>
            <h1>Operations copilot</h1>
          </div>
          <span className="copilot-capability"><Database size={13} /> Schema-aware · no API key</span>
        </div>
        <button className="icon-button workspace-close" aria-label="Close copilot" onClick={onClose} title="Close copilot (Esc)">
          <X size={18} />
        </button>
      </header>
      <div className="copilot-content" ref={scroll}>
        {history.length === 0 ? (
          <div className="copilot-welcome">
            <span className="welcome-mark"><Sparkles size={19} /></span>
            <span className="eyebrow">ASK YOUR NETWORK</span>
            <h2>What would you like to know?</h2>
            <p>Ask about flights, airports, aircraft, schedules, routes, weather, airspace, disruptions or operational risk. Answers explain the data they use.</p>
            <div className="copilot-suggestions">
              {examples.map((example) => (
                <button key={example} disabled={busy} onClick={() => void ask(example)}>
                  <MessageSquare size={15} /> <span>{example}</span><ArrowUp size={14} />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="copilot-thread" aria-live="polite">
            {history.map((exchange, index) => (
              <article className="copilot-exchange" key={`${index}-${exchange.question}`}>
                <div className="copilot-question"><span className="user-avatar">OP</span><p>{exchange.question}</p></div>
                {exchange.result ? (
                  <div className="copilot-response">
                    <div className="response-heading"><span className="tool-icon small"><Bot size={15} /></span><strong>AeroPulse</strong><span className="answer-mode"><Database size={12} /> Database answer</span></div>
                    <p className="answer-copy">{exchange.result.answer}</p>
                    {exchange.result.explanation && <div className="answer-basis"><span>HOW THIS WAS ANSWERED</span><p>{exchange.result.explanation}</p></div>}
                    {!!exchange.result.items.length && <div className="query-results">
                      <div className="result-caption">MATCHING RECORDS <span>{exchange.result.items.length}{exchange.result.truncated ? "+" : ""}</span></div>
                      {exchange.result.items.slice(0, 40).map((item, i) => (
                        <div className="query-item" key={i}>
                          {item.flight_id ? (
                            <button onClick={() => onSelect(item.flight_id!)}>
                              <strong>{item.flight_number}</strong>
                              <span>{item.origin && item.destination ? `${item.origin} → ${item.destination}` : item.route_code}</span>
                              {item.distance_km != null && <b>{Number(item.distance_km).toLocaleString(undefined, { maximumFractionDigits: 1 })} km</b>}
                              {item.flight_status && <small>{item.flight_status.replaceAll("_", " ").toLowerCase()}</small>}
                              {item.risk && <b className={item.risk.level.toLowerCase()}>{item.risk.level}</b>}
                            </button>
                          ) : <>
                            <strong>{item.iata_code ?? item.flight_number ?? item.route_code ?? item.zone_name ?? item.weather_type ?? item.registration_number ?? item.aircraft_id ?? item.flight_id ?? `Record ${i + 1}`}</strong>
                            <span>{Object.entries(item).filter(([key, value]) => value != null && !["iata_code", "flight_number", "route_code", "zone_name", "weather_type", "registration_number", "flight_id", "aircraft_id", "risk"].includes(key)).slice(0, 4).map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`).join(" · ")}</span>
                            {item.distance_km != null && <b>{Number(item.distance_km).toLocaleString(undefined, { maximumFractionDigits: 1 })} km</b>}
                          </>}
                        </div>
                      ))}
                      {exchange.result.truncated && <p className="muted result-limit">Showing the first 40 matching rows.</p>}
                    </div>}
                  </div>
                ) : exchange.error ? <p className="inline-error" role="alert">{exchange.error}</p> : index === history.length - 1 && busy ? <div className="copilot-response pending-answer" role="status"><span className="tool-icon small"><Bot size={15} /></span>Checking the operational database…</div> : null}
              </article>
            ))}
            {pendingQuestion && <span className="sr-only">Working on: {pendingQuestion}</span>}
          </div>
        )}
      </div>
      <div className="copilot-composer-wrap">
        <form className="copilot-input copilot-composer" onSubmit={submit}>
          <input aria-label="Operational question" placeholder="Ask about your operational data…" value={question} maxLength={300} onChange={(event) => setQuestion(event.target.value)} />
          <button aria-label="Submit question" disabled={busy || question.trim().length < 3}><ArrowUp size={18} /></button>
        </form>
        <p>Answers are grounded in the database. Check source and recency before operational decisions.</p>
      </div>
    </section>
  );
}

