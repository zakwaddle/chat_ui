import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const initialMessages = [
  {
    id: "system-welcome",
    role: "assistant",
    content: "Local chat skeleton is ready. Send a message to test the backend round trip.",
    memoryDebug: null
  }
];

function buildMemoryDebug(data) {
  return {
    retrievedMemories: data.retrieved_memories || [],
    prompt: data.prompt || {
      used_recalled_memories: false,
      recalled_memory_count: 0
    },
    retrieval: data.retrieval || {
      configured_memory_count: 0,
      similarity_threshold: null
    },
    expandedContextUsed: Boolean(data.context_expansion?.used)
  };
}

function MemoryDebugPanel({ debug }) {
  if (!debug) {
    return null;
  }

  const hits = debug.retrievedMemories;

  return (
    <details className="memory-debug">
      <summary>
        <span>Memory</span>
        <span>{hits.length} hits</span>
      </summary>

      <div className="memory-debug-body">
        <dl className="memory-debug-stats">
          <div>
            <dt>Recalled context</dt>
            <dd>{debug.prompt.used_recalled_memories ? "Used" : "Not used"}</dd>
          </div>
          <div>
            <dt>Expanded context</dt>
            <dd>{debug.expandedContextUsed ? "Used" : "Not used"}</dd>
          </div>
          <div>
            <dt>Threshold</dt>
            <dd>{debug.retrieval.similarity_threshold ?? "None"}</dd>
          </div>
        </dl>

        {hits.length > 0 ? (
          <ol className="memory-hit-list">
            {hits.map((hit) => (
              <li className="memory-hit" key={hit.message_id}>
                <div className="memory-hit-meta">
                  <span>#{hit.message_id}</span>
                  <span>{hit.role}</span>
                  <span>{hit.similarity.toFixed(3)}</span>
                </div>
                <p>{hit.content}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="memory-empty">No older memories were retrieved.</p>
        )}
      </div>
    </details>
  );
}

function splitThinking(content) {
  const text = String(content || "");
  const completeBlock = text.match(/<think[^>]*>([\s\S]*?)<\/think>/i);

  if (completeBlock) {
    return {
      thinking: completeBlock[1].trim(),
      answer: text.replace(completeBlock[0], "").trim()
    };
  }

  const closingTagIndex = text.toLowerCase().indexOf("</think>");
  if (closingTagIndex !== -1) {
    return {
      thinking: text.slice(0, closingTagIndex).trim(),
      answer: text.slice(closingTagIndex + "</think>".length).trim()
    };
  }

  return {
    thinking: "",
    answer: text
  };
}

function MessageContent({ message }) {
  if (message.role !== "assistant") {
    return <p>{message.content}</p>;
  }

  const { thinking, answer } = splitThinking(message.content);

  return (
    <>
      {thinking ? (
        <details className="thinking-panel">
          <summary>Thinking</summary>
          <pre>{thinking}</pre>
        </details>
      ) : null}
      <p>{answer || message.content}</p>
    </>
  );
}

function App() {
  const [messages, setMessages] = useState(initialMessages);
  const [conversationId, setConversationId] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [conversationTitle, setConversationTitle] = useState("");
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [error, setError] = useState("");

  const canSend = useMemo(() => draft.trim().length > 0 && !isSending, [draft, isSending]);
  const activeConversation = conversations.find((conversation) => conversation.id === conversationId);

  useEffect(() => {
    loadConversations();
  }, []);

  async function loadConversations() {
    setIsLoadingConversations(true);
    try {
      const response = await fetch("/api/conversations");
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Unable to load conversations");
      }

      setConversations(data.conversations || []);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load conversations");
    } finally {
      setIsLoadingConversations(false);
    }
  }

  async function createNewConversation() {
    setError("");

    try {
      const response = await fetch("/api/conversations", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ title: conversationTitle.trim() || undefined })
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Unable to create conversation");
      }

      const conversation = data.conversation;
      setConversationId(conversation.id);
      setConversationTitle("");
      setMessages([]);
      await loadConversations();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to create conversation");
    }
  }

  async function openConversation(nextConversationId) {
    setError("");

    try {
      const response = await fetch(`/api/conversations/${nextConversationId}/messages`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Unable to open conversation");
      }

      setConversationId(nextConversationId);
      setMessages(data.messages || []);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to open conversation");
    }
  }

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
        body: JSON.stringify({ message: content, conversation_id: conversationId })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Backend request failed");
      }

      setConversationId(data.conversation?.id || conversationId);
      await loadConversations();
      setMessages((current) =>
        current.map((message) =>
          message.id === userMessage.id ? data.user_message || message : message
        ).concat(
          data.assistant_message
            ? [
                {
                  ...data.assistant_message,
                  memoryDebug: buildMemoryDebug(data)
                }
              ]
            : []
        )
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to send message");
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="chat-panel" aria-label="Associative chat">
        <aside className="conversation-sidebar" aria-label="Conversations">
          <div className="conversation-sidebar-header">
            <h2>Conversations</h2>
            <button type="button" onClick={loadConversations} disabled={isLoadingConversations}>
              Refresh
            </button>
          </div>

          <div className="new-conversation">
            <label htmlFor="conversation-title">Title</label>
            <input
              id="conversation-title"
              value={conversationTitle}
              onChange={(event) => setConversationTitle(event.target.value)}
              placeholder="Optional title"
            />
            <button type="button" onClick={createNewConversation}>
              New
            </button>
          </div>

          <div className="conversation-list">
            {conversations.length > 0 ? (
              conversations.map((conversation) => (
                <button
                  className={`conversation-item ${
                    conversation.id === conversationId ? "conversation-item-active" : ""
                  }`}
                  type="button"
                  key={conversation.id}
                  onClick={() => openConversation(conversation.id)}
                >
                  <span>{conversation.title}</span>
                  <small>{conversation.message_count} messages</small>
                </button>
              ))
            ) : (
              <p>{isLoadingConversations ? "Loading..." : "No conversations yet."}</p>
            )}
          </div>
        </aside>

        <section className="chat-main" aria-label="Current conversation">
        <header className="chat-header">
          <div>
            <h1>Associative Chat</h1>
            <p>{activeConversation?.title || "Bounded memory prototype"}</p>
          </div>
          <span className="status-pill">Phase 11</span>
        </header>

        <div className="message-list" aria-live="polite">
          {messages.map((message) => (
            <article className={`message message-${message.role}`} key={message.id}>
              <div className="message-role">{message.role}</div>
              <MessageContent message={message} />
              {message.role === "assistant" ? <MemoryDebugPanel debug={message.memoryDebug} /> : null}
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
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
