import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const THEME_STORAGE_KEY = "associative-chat-theme";
const TEMPERATURE_STORAGE_KEY = "associative-chat-temperature";
const REPEAT_PENALTY_STORAGE_KEY = "associative-chat-repeat-penalty";
const ACTIVE_CONVERSATION_STORAGE_KEY = "associative-chat-active-conversation";
const LLAMA_SETTINGS_STORAGE_KEY = "associative-chat-llama-settings";

const initialMessages = [
  {
    id: "system-welcome",
    role: "assistant",
    content: "Local chat skeleton is ready. Send a message to test the backend round trip.",
    memoryDebug: null
  }
];

function readInitialTheme() {
  const savedTheme = globalThis.localStorage?.getItem(THEME_STORAGE_KEY);
  if (savedTheme === "light" || savedTheme === "dark") {
    return savedTheme;
  }

  return globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readStoredValue(key, fallback) {
  return globalThis.localStorage?.getItem(key) || fallback;
}

function readStoredJson(key, fallback) {
  try {
    const value = globalThis.localStorage?.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

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

function parseInlineMarkdown(text) {
  const nodes = [];
  const pattern = /(\[[^\]]+\]\((https?:\/\/[^)\s]+)\)|`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*)/g;
  let lastIndex = 0;
  let match;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    if (match[2]) {
      nodes.push(
        <a href={match[2]} key={nodes.length} rel="noreferrer" target="_blank">
          {match[1].slice(1, match[1].indexOf("]"))}
        </a>
      );
    } else if (match[3]) {
      nodes.push(<code key={nodes.length}>{match[3]}</code>);
    } else if (match[4]) {
      nodes.push(<strong key={nodes.length}>{match[4]}</strong>);
    } else if (match[5]) {
      nodes.push(<em key={nodes.length}>{match[5]}</em>);
    }

    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

function MarkdownContent({ content }) {
  const text = String(content || "");
  const lines = text.split(/\r?\n/);
  const blocks = [];
  let index = 0;

  function addParagraph(startIndex) {
    const paragraphLines = [];

    while (index < lines.length) {
      const line = lines[index];
      if (
        !line.trim() ||
        line.startsWith("```") ||
        /^#{1,3}\s+/.test(line) ||
        /^\s*[-*]\s+/.test(line) ||
        /^\s*\d+\.\s+/.test(line) ||
        /^\s*>\s?/.test(line)
      ) {
        break;
      }

      paragraphLines.push(line.trim());
      index += 1;
    }

    blocks.push(<p key={`p-${startIndex}`}>{parseInlineMarkdown(paragraphLines.join(" "))}</p>);
  }

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const startIndex = index;
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      index += index < lines.length ? 1 : 0;
      blocks.push(
        <pre className="markdown-code-block" key={`code-${startIndex}`}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const Tag = `h${level + 2}`;
      blocks.push(<Tag key={`h-${index}`}>{parseInlineMarkdown(heading[2])}</Tag>);
      index += 1;
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const startIndex = index;
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ul key={`ul-${startIndex}`}>
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{parseInlineMarkdown(item)}</li>
          ))}
        </ul>
      );
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const startIndex = index;
      const items = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ol key={`ol-${startIndex}`}>
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{parseInlineMarkdown(item)}</li>
          ))}
        </ol>
      );
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const startIndex = index;
      const quoteLines = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      blocks.push(<blockquote key={`quote-${startIndex}`}>{parseInlineMarkdown(quoteLines.join(" "))}</blockquote>);
      continue;
    }

    addParagraph(index);
  }

  return <div className="message-markdown">{blocks}</div>;
}

function MessageContent({ message }) {
  if (message.role !== "assistant") {
    return <MarkdownContent content={message.content} />;
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
      <MarkdownContent content={answer || message.content} />
    </>
  );
}

function createClientId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  return `client-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

async function readJsonStream(response, onEvent) {
  if (!response.body) {
    const text = await response.text();
    text
      .split("\n")
      .filter((line) => line.trim())
      .forEach((line) => onEvent(JSON.parse(line)));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }

      onEvent(JSON.parse(line));
    }

    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    onEvent(JSON.parse(buffer));
  }
}

function App() {
  const [theme, setTheme] = useState(readInitialTheme);
  const [messages, setMessages] = useState(initialMessages);
  const [conversationId, setConversationId] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [conversationTitle, setConversationTitle] = useState("");
  const [draft, setDraft] = useState("");
  const [temperature, setTemperature] = useState(() => readStoredValue(TEMPERATURE_STORAGE_KEY, "0.7"));
  const [repeatPenalty, setRepeatPenalty] = useState(() => readStoredValue(REPEAT_PENALTY_STORAGE_KEY, "1.1"));
  const [llamaModels, setLlamaModels] = useState([]);
  const [llamaStatus, setLlamaStatus] = useState(null);
  const [llamaSettings, setLlamaSettings] = useState(() => readStoredJson(LLAMA_SETTINGS_STORAGE_KEY, {}));
  const [isSending, setIsSending] = useState(false);
  const [isRecordingVoice, setIsRecordingVoice] = useState(false);
  const [isTranscribingVoice, setIsTranscribingVoice] = useState(false);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingLlama, setIsLoadingLlama] = useState(false);
  const [isUpdatingLlama, setIsUpdatingLlama] = useState(false);
  const [error, setError] = useState("");
  const [copiedMessageId, setCopiedMessageId] = useState(null);
  const messageListRef = useRef(null);
  const messageEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const voiceChunksRef = useRef([]);
  const voiceStreamRef = useRef(null);
  const hasRestoredConversationRef = useRef(false);
  const shouldStickToBottomRef = useRef(true);

  const canSend = useMemo(() => draft.trim().length > 0 && !isSending, [draft, isSending]);
  const activeConversation = conversations.find((conversation) => conversation.id === conversationId);

  useEffect(() => {
    loadConversations();
    loadLlamaRuntime();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem(TEMPERATURE_STORAGE_KEY, temperature);
  }, [temperature]);

  useEffect(() => {
    localStorage.setItem(REPEAT_PENALTY_STORAGE_KEY, repeatPenalty);
  }, [repeatPenalty]);

  useEffect(() => {
    localStorage.setItem(LLAMA_SETTINGS_STORAGE_KEY, JSON.stringify(llamaSettings));
  }, [llamaSettings]);

  useEffect(() => {
    if (conversationId) {
      localStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, String(conversationId));
    }
  }, [conversationId]);

  useEffect(() => {
    if (shouldStickToBottomRef.current) {
      messageEndRef.current?.scrollIntoView({ block: "end" });
    }
  }, [messages]);

  useEffect(
    () => () => {
      stopVoiceTracks();
    },
    []
  );

  function toggleTheme() {
    setTheme((currentTheme) => (currentTheme === "dark" ? "light" : "dark"));
  }

  async function loadConversations() {
    setIsLoadingConversations(true);
    try {
      const response = await fetch("/api/conversations");
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Unable to load conversations");
      }

      const nextConversations = data.conversations || [];
      setConversations(nextConversations);

      if (!hasRestoredConversationRef.current && !conversationId) {
        hasRestoredConversationRef.current = true;
        const savedConversationId = Number(localStorage.getItem(ACTIVE_CONVERSATION_STORAGE_KEY));
        if (savedConversationId && nextConversations.some((conversation) => conversation.id === savedConversationId)) {
          await openConversation(savedConversationId);
        }
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load conversations");
    } finally {
      setIsLoadingConversations(false);
    }
  }

  async function loadLlamaRuntime() {
    setIsLoadingLlama(true);
    try {
      const [modelsResponse, statusResponse] = await Promise.all([
        fetch("/api/llama/models"),
        fetch("/api/llama/status")
      ]);
      const modelsData = await modelsResponse.json();
      const statusData = await statusResponse.json();

      if (!modelsResponse.ok) {
        throw new Error(modelsData.error || "Unable to load GGUF models");
      }
      if (!statusResponse.ok) {
        throw new Error(statusData.error || "Unable to load llama server status");
      }

      const defaults = modelsData.defaults || {};
      setLlamaModels(modelsData.models || []);
      setLlamaStatus(statusData);
      setLlamaSettings((currentSettings) => ({
        ...defaults,
        ...currentSettings
      }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load llama server controls");
    } finally {
      setIsLoadingLlama(false);
    }
  }

  async function updateLlamaServer(action) {
    setIsUpdatingLlama(true);
    setError("");

    try {
      const response = await fetch(`/api/llama/${action}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: action === "stop" ? undefined : JSON.stringify(buildLlamaLaunchPayload(llamaSettings))
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || `Unable to ${action} llama server`);
      }

      setLlamaStatus(data);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : `Unable to ${action} llama server`);
    } finally {
      setIsUpdatingLlama(false);
    }
  }

  function setLlamaSetting(name, value) {
    setLlamaSettings((currentSettings) => ({
      ...currentSettings,
      [name]: value
    }));
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
      localStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, String(conversation.id));
      setConversationTitle("");
      shouldStickToBottomRef.current = true;
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
      localStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, String(nextConversationId));
      shouldStickToBottomRef.current = true;
      setMessages(data.messages || []);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to open conversation");
    }
  }

  async function sendMessage(event) {
    event?.preventDefault();

    const content = draft.trim();
    if (!content) {
      return;
    }

    const userMessage = {
      id: createClientId(),
      role: "user",
      content
    };
    const assistantMessageId = createClientId();

    shouldStickToBottomRef.current = true;
    setMessages((current) => [
      ...current,
      userMessage,
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        memoryDebug: null,
        isStreaming: true
      }
    ]);
    setDraft("");
    setError("");
    setIsSending(true);

    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          message: content,
          conversation_id: conversationId,
          generation: {
            temperature,
            repeat_penalty: repeatPenalty
          }
        })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || "Backend request failed");
      }

      let latestData = null;
      await readJsonStream(response, ({ event: eventName, data }) => {
        if (eventName === "conversation") {
          setConversationId(data.conversation?.id || conversationId);
          return;
        }

        if (eventName === "user_message") {
          setMessages((current) =>
            current.map((message) => (message.id === userMessage.id ? data.user_message || message : message))
          );
          return;
        }

        if (eventName === "delta") {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...message,
                    content: `${message.content || ""}${data.content || ""}`
                  }
                : message
            )
          );
          return;
        }

        if (eventName === "assistant_message") {
          latestData = data;
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId
                ? {
                    ...data.assistant_message,
                    memoryDebug: buildMemoryDebug(data),
                    isStreaming: false
                  }
                : message
            )
          );
          return;
        }

        if (eventName === "error") {
          throw new Error(data.error || "Backend request failed");
        }
      });

      if (latestData?.conversation?.id) {
        setConversationId(latestData.conversation.id);
      }
      await loadConversations();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to send message");
      setMessages((current) =>
        current.filter((message) => message.id !== assistantMessageId || (message.content || "").trim())
      );
    } finally {
      setIsSending(false);
    }
  }

  async function copyMessageContent(message) {
    const content = String(message.content || "");
    if (!content) {
      return;
    }

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(content);
      } else {
        const textArea = document.createElement("textarea");
        textArea.value = content;
        textArea.style.position = "fixed";
        textArea.style.opacity = "0";
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand("copy");
        document.body.removeChild(textArea);
      }

      setCopiedMessageId(message.id);
      window.setTimeout(() => setCopiedMessageId(null), 1600);
    } catch (copyError) {
      setError(copyError instanceof Error ? copyError.message : "Unable to copy message");
    }
  }

  async function toggleVoiceRecording() {
    if (isRecordingVoice) {
      mediaRecorderRef.current?.stop();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Voice input is not available in this browser.");
      return;
    }

    setError("");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = selectRecorderMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

      voiceStreamRef.current = stream;
      voiceChunksRef.current = [];
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data?.size) {
          voiceChunksRef.current.push(event.data);
        }
      };

      recorder.onerror = () => {
        setError("Voice recording failed.");
        setIsRecordingVoice(false);
        setIsTranscribingVoice(false);
        stopVoiceTracks();
      };

      recorder.onstop = () => {
        const chunks = voiceChunksRef.current;
        const type = recorder.mimeType || mimeType || "audio/webm";
        mediaRecorderRef.current = null;
        voiceChunksRef.current = [];
        setIsRecordingVoice(false);
        stopVoiceTracks();

        if (chunks.length > 0) {
          transcribeVoiceBlob(new Blob(chunks, { type }));
        }
      };

      recorder.start();
      setIsRecordingVoice(true);
    } catch (recordingError) {
      stopVoiceTracks();
      setIsRecordingVoice(false);
      setError(recordingError instanceof Error ? recordingError.message : "Unable to start voice recording");
    }
  }

  async function transcribeVoiceBlob(blob) {
    setIsTranscribingVoice(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("audio", blob, voiceFilenameForBlob(blob));

      const response = await fetch("/api/voice/transcribe", {
        method: "POST",
        body: formData
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Unable to transcribe voice input");
      }

      const transcript = String(data.transcript || "").trim();
      if (transcript) {
        setDraft((currentDraft) => {
          const separator = currentDraft.trim() ? "\n" : "";
          return `${currentDraft}${separator}${transcript}`;
        });
      }
    } catch (transcriptionError) {
      setError(transcriptionError instanceof Error ? transcriptionError.message : "Unable to transcribe voice input");
    } finally {
      setIsTranscribingVoice(false);
    }
  }

  function stopVoiceTracks() {
    voiceStreamRef.current?.getTracks().forEach((track) => track.stop());
    voiceStreamRef.current = null;
  }

  function handleMessageKeyDown(event) {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }

    if (event.metaKey || event.ctrlKey || !event.altKey) {
      event.preventDefault();
      if (canSend) {
        sendMessage(event);
      }
    }
  }

  function handleMessageListScroll(event) {
    const element = event.currentTarget;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    shouldStickToBottomRef.current = distanceFromBottom < 80;
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

          <section className="llama-panel" aria-label="Llama server management">
            <div className="llama-panel-header">
              <h2>llama.cpp</h2>
              <button type="button" onClick={loadLlamaRuntime} disabled={isLoadingLlama || isUpdatingLlama}>
                Refresh
              </button>
            </div>

            <div className="llama-status-row">
              <span className={`llama-state ${llamaStatus?.endpoint_reachable ? "llama-state-online" : ""}`}>
                {llamaStatus?.endpoint_reachable ? "Online" : "Offline"}
              </span>
              <span>{llamaStatus?.process_state || "unknown"}</span>
            </div>

            <label>
              <span>Chat model</span>
              <select
                value={llamaSettings.model_path || ""}
                onChange={(event) => setLlamaSetting("model_path", event.target.value)}
              >
                <option value="">Select GGUF</option>
                {llamaModels
                  .filter((model) => !model.is_embedding)
                  .map((model) => (
                    <option value={model.path} key={model.path}>
                      {model.name}
                    </option>
                  ))}
              </select>
            </label>

            <label>
              <span>Embedding model</span>
              <select
                value={llamaSettings.embedding_model_path || ""}
                onChange={(event) => setLlamaSetting("embedding_model_path", event.target.value)}
              >
                <option value="">Select GGUF</option>
                {llamaModels.map((model) => (
                  <option value={model.path} key={model.path}>
                    {model.name}
                  </option>
                ))}
              </select>
            </label>

            <div className="llama-grid">
              <label>
                <span>GPU layers</span>
                <input
                  min="0"
                  type="number"
                  value={llamaSettings.gpu_layers ?? ""}
                  onChange={(event) => setLlamaSetting("gpu_layers", event.target.value)}
                />
              </label>
              <label>
                <span>Context</span>
                <input
                  min="1"
                  type="number"
                  value={llamaSettings.context_size ?? ""}
                  onChange={(event) => setLlamaSetting("context_size", event.target.value)}
                />
              </label>
              <label>
                <span>Batch</span>
                <input
                  min="1"
                  type="number"
                  value={llamaSettings.batch_size ?? ""}
                  onChange={(event) => setLlamaSetting("batch_size", event.target.value)}
                />
              </label>
              <label>
                <span>Threads</span>
                <input
                  min="1"
                  type="number"
                  value={llamaSettings.threads ?? ""}
                  onChange={(event) => setLlamaSetting("threads", event.target.value)}
                />
              </label>
            </div>

            <div className="llama-grid">
              <label>
                <span>Port</span>
                <input
                  min="1"
                  type="number"
                  value={llamaSettings.port ?? ""}
                  onChange={(event) => setLlamaSetting("port", event.target.value)}
                />
              </label>
              <label>
                <span>Temp</span>
                <input
                  min="0"
                  step="0.05"
                  type="number"
                  value={llamaSettings.temperature ?? ""}
                  onChange={(event) => setLlamaSetting("temperature", event.target.value)}
                />
              </label>
            </div>

            <div className="llama-actions">
              <button type="button" onClick={() => updateLlamaServer("start")} disabled={isUpdatingLlama}>
                Start
              </button>
              <button type="button" onClick={() => updateLlamaServer("restart")} disabled={isUpdatingLlama}>
                Restart
              </button>
              <button type="button" onClick={() => updateLlamaServer("stop")} disabled={isUpdatingLlama}>
                Stop
              </button>
            </div>
          </section>

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
          <div className="header-actions">
            <button className="theme-toggle" type="button" onClick={toggleTheme}>
              {theme === "dark" ? "Light" : "Dark"}
            </button>
            <span className="status-pill">Phase 11</span>
          </div>
        </header>

        <div className="message-list" ref={messageListRef} onScroll={handleMessageListScroll} aria-live="polite">
          {messages.map((message) => (
            <article className={`message message-${message.role}`} key={message.id}>
              <div className="message-meta">
                <div className="message-role">{message.role}</div>
                {message.role === "assistant" && message.content ? (
                  <button className="message-copy" type="button" onClick={() => copyMessageContent(message)}>
                    {copiedMessageId === message.id ? "Copied" : "Copy"}
                  </button>
                ) : null}
              </div>
              <MessageContent message={message} />
              {message.isStreaming ? (
                <p className="streaming-placeholder">
                  <span className="streaming-dots" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </span>
                  {message.content ? "Generating" : "Thinking"}
                </p>
              ) : null}
              {message.role === "assistant" ? <MemoryDebugPanel debug={message.memoryDebug} /> : null}
            </article>
          ))}
          <div ref={messageEndRef} />
        </div>

        {error ? (
          <div className="error-banner">
            <span>{error}</span>
            <button type="button" onClick={() => setError("")}>
              Dismiss
            </button>
          </div>
        ) : null}

        <form className="composer" onSubmit={sendMessage}>
          <div className="generation-controls" aria-label="Generation settings">
            <label>
              <span>Temperature</span>
              <input
                min="0"
                step="0.05"
                type="number"
                value={temperature}
                onChange={(event) => setTemperature(event.target.value)}
              />
            </label>
            <label>
              <span>Repeat penalty</span>
              <input
                min="0"
                step="0.05"
                type="number"
                value={repeatPenalty}
                onChange={(event) => setRepeatPenalty(event.target.value)}
              />
            </label>
          </div>
          <label className="message-label" htmlFor="message">Message</label>
          <textarea
            id="message"
            rows="3"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleMessageKeyDown}
            placeholder="Type a message..."
          />
          <button
            className={`voice-button ${isRecordingVoice ? "voice-button-recording" : ""}`}
            type="button"
            onClick={toggleVoiceRecording}
            disabled={isSending || isTranscribingVoice}
            aria-pressed={isRecordingVoice}
            title={isRecordingVoice ? "Stop recording" : "Record voice input"}
          >
            {isRecordingVoice ? "Stop" : isTranscribingVoice ? "..." : "Mic"}
          </button>
          <button type="submit" disabled={!canSend}>
            Send
          </button>
        </form>
        </section>
      </section>
    </main>
  );
}

function selectRecorderMimeType() {
  const supportedTypes = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
  return supportedTypes.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function voiceFilenameForBlob(blob) {
  if (blob.type.includes("ogg")) {
    return "voice.ogg";
  }
  if (blob.type.includes("wav")) {
    return "voice.wav";
  }

  return "voice.webm";
}

function buildLlamaLaunchPayload(settings) {
  return {
    ...settings,
    port: numberOrEmpty(settings.port),
    context_size: numberOrEmpty(settings.context_size),
    batch_size: numberOrEmpty(settings.batch_size),
    gpu_layers: numberOrEmpty(settings.gpu_layers),
    threads: numberOrEmpty(settings.threads),
    temperature: numberOrEmpty(settings.temperature),
    repeat_penalty: numberOrEmpty(settings.repeat_penalty)
  };
}

function numberOrEmpty(value) {
  if (value === "" || value === null || value === undefined) {
    return "";
  }

  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : "";
}

createRoot(document.getElementById("root")).render(<App />);
