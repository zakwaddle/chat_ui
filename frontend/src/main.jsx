import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const initialMessages = [
  {
    id: "system-welcome",
    role: "assistant",
    content: "Local chat skeleton is ready. Send a message to test the backend round trip."
  }
];

function App() {
  const [messages, setMessages] = useState(initialMessages);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");

  const canSend = useMemo(() => draft.trim().length > 0 && !isSending, [draft, isSending]);

  async function sendMessage(event) {
    event.preventDefault();

    const content = draft.trim();
    if (!content) {
      return;
    }

    const userMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content
    };

    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setError("");
    setIsSending(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ message: content })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Backend request failed");
      }

      setMessages((current) => [
        ...current,
        {
          id: data.id || crypto.randomUUID(),
          role: data.role || "assistant",
          content: data.content || ""
        }
      ]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to send message");
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="chat-panel" aria-label="Associative chat">
        <header className="chat-header">
          <div>
            <h1>Associative Chat</h1>
            <p>Bounded memory prototype</p>
          </div>
          <span className="status-pill">Phase 1</span>
        </header>

        <div className="message-list" aria-live="polite">
          {messages.map((message) => (
            <article className={`message message-${message.role}`} key={message.id}>
              <div className="message-role">{message.role}</div>
              <p>{message.content}</p>
            </article>
          ))}
          {isSending ? (
            <article className="message message-assistant">
              <div className="message-role">assistant</div>
              <p>Thinking...</p>
            </article>
          ) : null}
        </div>

        {error ? <div className="error-banner">{error}</div> : null}

        <form className="composer" onSubmit={sendMessage}>
          <label htmlFor="message">Message</label>
          <textarea
            id="message"
            rows="3"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Type a message..."
          />
          <button type="submit" disabled={!canSend}>
            Send
          </button>
        </form>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
