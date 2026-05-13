import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";

const MODE_LABELS = {
  dreamer:  { th: "Career Dreamer",  desc: "สำรวจความสนใจและวางแผนอาชีพ", icon: "🌟" },
  tcas_rag: { th: "TCAS Advisor",    desc: "ตรวจสอบสิทธิ์และเปรียบเทียบคณะ",  icon: "🎓" },
};

function truncateName(text, max = 40) {
  if (!text) return null;
  const clean = text.trim();
  return clean.length <= max ? clean : clean.slice(0, max).trimEnd() + "…";
}

const s = {
  container: {
    display: "flex",
    height: "calc(100vh - 120px)",
    gap: 0,
    background: "#fff",
    borderRadius: 12,
    overflow: "hidden",
    border: "1px solid #e0e0e0",
  },
  sidebar: {
    width: 240,
    background: "#1a1a2e",
    display: "flex",
    flexDirection: "column",
    flexShrink: 0,
  },
  sidebarHeader: {
    padding: "16px 14px 12px",
    borderBottom: "1px solid rgba(255,255,255,.1)",
  },
  newChatBtn: {
    width: "100%",
    padding: "9px 12px",
    background: "#0f3460",
    color: "#fff",
    border: "1.5px solid rgba(255,255,255,.25)",
    borderRadius: 8,
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 600,
    textAlign: "left",
  },
  sessionList: { flex: 1, overflowY: "auto", padding: "8px 0" },
  sessionItem: (active) => ({
    padding: "10px 14px",
    cursor: "pointer",
    background: active ? "rgba(255,255,255,.12)" : "transparent",
    borderLeft: active ? "3px solid #e94560" : "3px solid transparent",
    transition: "background .15s",
    position: "relative",
  }),
  sessionMode: { fontSize: 11, color: "#aaa", textTransform: "uppercase", letterSpacing: .5, marginBottom: 2 },
  sessionName: { fontSize: 13, color: "#eee", lineHeight: 1.4, wordBreak: "break-word", paddingRight: 20 },
  deleteBtn: {
    position: "absolute",
    top: "50%",
    right: 8,
    transform: "translateY(-50%)",
    background: "none",
    border: "none",
    color: "#888",
    cursor: "pointer",
    fontSize: 14,
    padding: "2px 4px",
    borderRadius: 4,
    lineHeight: 1,
    display: "none",
  },
  sessionNameInput: {
    width: "100%",
    background: "rgba(255,255,255,.1)",
    border: "1px solid rgba(255,255,255,.3)",
    borderRadius: 4,
    color: "#fff",
    fontSize: 13,
    padding: "2px 6px",
    outline: "none",
    fontFamily: "Sarabun, sans-serif",
    boxSizing: "border-box",
  },

  main: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0 },

  modeScreen: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 16,
    padding: 32,
    background: "#f8f9ff",
  },
  modeTitle: { fontSize: 22, fontWeight: 700, color: "#0f3460", marginBottom: 8 },
  modeCards: { display: "flex", gap: 16 },
  modeCard: (hover) => ({
    width: 200,
    padding: "24px 20px",
    border: `2px solid ${hover ? "#0f3460" : "#dde"}`,
    borderRadius: 12,
    cursor: "pointer",
    background: hover ? "#eef2ff" : "#fff",
    textAlign: "center",
    transition: "all .15s",
  }),
  modeIcon: { fontSize: 36, marginBottom: 8 },
  modeName: { fontWeight: 700, color: "#0f3460", marginBottom: 4 },
  modeDesc: { fontSize: 13, color: "#666" },

  chatHeader: {
    padding: "10px 20px",
    borderBottom: "1px solid #e0e0e0",
    display: "flex",
    alignItems: "center",
    gap: 10,
    background: "#fafafa",
    flexShrink: 0,
  },
  chatHeaderTitle: { fontSize: 14, fontWeight: 600, color: "#333", flex: 1 },
  modePill: (active) => ({
    display: "flex",
    alignItems: "center",
    gap: 5,
    padding: "4px 10px",
    borderRadius: 20,
    border: "1.5px solid",
    borderColor: active ? "#0f3460" : "#ccc",
    background: active ? "#eef2ff" : "#f5f5f5",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
    color: active ? "#0f3460" : "#888",
    transition: "all .15s",
  }),

  messages: {
    flex: 1,
    overflowY: "auto",
    padding: "20px 24px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  bubble: (role) => ({
    maxWidth: "72%",
    alignSelf: role === "user" ? "flex-end" : "flex-start",
    background: role === "user" ? "#0f3460" : "#f1f3f9",
    color: role === "user" ? "#fff" : "#222",
    padding: "12px 16px",
    borderRadius: role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
    fontSize: 14,
    lineHeight: 1.6,
  }),
  inputRow: {
    padding: "14px 20px",
    borderTop: "1px solid #e0e0e0",
    display: "flex",
    gap: 10,
    background: "#fff",
  },
  textarea: {
    flex: 1,
    padding: "10px 14px",
    border: "1.5px solid #ddd",
    borderRadius: 10,
    fontSize: 14,
    resize: "none",
    fontFamily: "Sarabun, sans-serif",
    lineHeight: 1.5,
  },
  sendBtn: (disabled) => ({
    padding: "0 20px",
    background: disabled ? "#ccc" : "#0f3460",
    color: "#fff",
    border: "none",
    borderRadius: 10,
    cursor: disabled ? "default" : "pointer",
    fontWeight: 600,
    fontSize: 14,
    whiteSpace: "nowrap",
  }),
  typingDot: {
    display: "inline-block",
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "#999",
    margin: "0 2px",
    animation: "bounce 1s infinite",
  },
};

function TypingIndicator() {
  return (
    <div style={s.bubble("assistant")}>
      <span style={s.typingDot} />
      <span style={{ ...s.typingDot, animationDelay: ".2s" }} />
      <span style={{ ...s.typingDot, animationDelay: ".4s" }} />
    </div>
  );
}

export default function ChatInterface({ getToken }) {
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [pendingMode, setPendingMode] = useState(null); // chosen mode before first message
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [hoveredMode, setHoveredMode] = useState(null);
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const bottomRef = useRef(null);
  const renameInputRef = useRef(null);

  useEffect(() => { loadSessions(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, sending]);
  useEffect(() => { if (renamingId) renameInputRef.current?.focus(); }, [renamingId]);

  async function api(path, opts = {}) {
    const token = await getToken();
    const res = await fetch(path, {
      ...opts,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...opts.headers },
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }

  async function loadSessions() {
    try {
      const data = await api("/api/chat/sessions");
      setSessions(data.sessions || []);
    } catch { /* graceful */ }
  }

  async function selectSession(session) {
    setActiveSession(session);
    setPendingMode(null);
    try {
      const data = await api(`/api/chat/${session.id}/messages`);
      setMessages(data.messages || []);
    } catch { setMessages([]); }
  }

  function pickMode(mode) {
    // Don't create session yet — wait for first message
    setPendingMode(mode);
    setActiveSession(null);
    setMessages([]);
  }

  async function switchMode(mode) {
    if (!activeSession || mode === activeSession.ai_mode) return;
    try {
      await api(`/api/chat/${activeSession.id}/mode`, {
        method: "PATCH",
        body: JSON.stringify({ ai_mode: mode }),
      });
      const updated = { ...activeSession, ai_mode: mode };
      setActiveSession(updated);
      setSessions((prev) => prev.map((s) => s.id === updated.id ? updated : s));
    } catch (e) { alert("ไม่สามารถเปลี่ยนโหมดได้: " + e.message); }
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);

    let session = activeSession;

    // Lazy session creation — create on first message
    if (!session && pendingMode) {
      try {
        const data = await api("/api/chat/session", {
          method: "POST",
          body: JSON.stringify({ ai_mode: pendingMode }),
        });
        session = { id: data.session_id, ai_mode: data.ai_mode, name: null };
        setActiveSession(session);
        setSessions((prev) => [session, ...prev]);
        setPendingMode(null);
      } catch (e) {
        setSending(false);
        alert("ไม่สามารถสร้างเซสชันได้: " + e.message);
        return;
      }
    }

    if (!session) { setSending(false); return; }

    setMessages((prev) => [...prev, { role: "user", content: text }]);

    try {
      const data = await api(`/api/chat/${session.id}/message`, {
        method: "POST",
        body: JSON.stringify({ content: text }),
      });
      setMessages((prev) => [...prev, { role: data.role, content: data.content }]);

      // Auto-name the session from the first user message
      if (!session.name) {
        const autoName = truncateName(text);
        if (autoName) {
          await api(`/api/chat/${session.id}/name`, {
            method: "PATCH",
            body: JSON.stringify({ name: autoName }),
          });
          const named = { ...session, name: autoName };
          setActiveSession(named);
          setSessions((prev) => prev.map((s) => s.id === named.id ? named : s));
        }
      }
    } catch (e) {
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ เกิดข้อผิดพลาด: ${e.message}` }]);
    } finally { setSending(false); }
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  }

  async function deleteSession(sess, e) {
    e.stopPropagation();
    if (!confirm(`ลบแชท "${sess.name || "แชทใหม่"}" ?`)) return;
    try {
      await api(`/api/chat/${sess.id}`, { method: "DELETE" });
      setSessions((prev) => prev.filter((s) => s.id !== sess.id));
      if (activeSession?.id === sess.id) {
        setActiveSession(null);
        setMessages([]);
        setPendingMode(null);
      }
    } catch (e) { alert("ลบไม่สำเร็จ: " + e.message); }
  }

  function startRename(sess, e) {
    e.stopPropagation();
    setRenamingId(sess.id);
    setRenameValue(sess.name || "");
  }

  async function commitRename(sessId) {
    setRenamingId(null);
    const name = renameValue.trim();
    try {
      await api(`/api/chat/${sessId}/name`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      });
      setSessions((prev) => prev.map((s) => s.id === sessId ? { ...s, name: name || null } : s));
      if (activeSession?.id === sessId) setActiveSession((s) => ({ ...s, name: name || null }));
    } catch { /* ignore */ }
  }

  const currentMode = activeSession?.ai_mode || pendingMode;

  return (
    <>
      <style>{`
        @keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }
        .msg-content p{margin:0 0 6px} .msg-content p:last-child{margin:0}
        .msg-content table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px}
        .msg-content th,.msg-content td{border:1px solid #ccc;padding:6px 10px;text-align:left}
        .msg-content th{background:#e8ecf8;font-weight:600}
        .msg-content ul,.msg-content ol{margin:4px 0;padding-left:20px}
        .msg-content code{background:rgba(0,0,0,.08);padding:1px 5px;border-radius:4px;font-size:13px}
        .msg-content pre{background:#1e1e2e;color:#cdd6f4;padding:12px;border-radius:8px;overflow-x:auto;font-size:13px}
        .session-item:hover .rename-hint{opacity:1}
        .rename-hint{opacity:0;transition:opacity .15s;font-size:10px;color:#aaa;margin-top:2px}
        .session-item:hover .delete-btn{display:block!important}
        .delete-btn:hover{color:#e94560!important}
      `}</style>

      <div style={s.container}>
        {/* Sidebar */}
        <div style={s.sidebar}>
          <div style={s.sidebarHeader}>
            <button style={s.newChatBtn} onClick={() => { setActiveSession(null); setMessages([]); setPendingMode(null); }}>
              + แชทใหม่
            </button>
          </div>
          <div style={s.sessionList}>
            {sessions.map((sess) => (
              <div
                key={sess.id}
                className="session-item"
                style={s.sessionItem(activeSession?.id === sess.id)}
                onClick={() => selectSession(sess)}
              >
                <div style={s.sessionMode}>{MODE_LABELS[sess.ai_mode]?.icon} {MODE_LABELS[sess.ai_mode]?.th || sess.ai_mode}</div>
                <button
                  className="delete-btn"
                  style={s.deleteBtn}
                  onClick={(e) => deleteSession(sess, e)}
                  title="ลบแชท"
                >×</button>
                {renamingId === sess.id ? (
                  <input
                    ref={renameInputRef}
                    style={s.sessionNameInput}
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => commitRename(sess.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitRename(sess.id);
                      if (e.key === "Escape") setRenamingId(null);
                    }}
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <>
                    <div style={s.sessionName} onDoubleClick={(e) => startRename(sess, e)}>
                      {sess.name || <span style={{ color: "#888", fontStyle: "italic" }}>แชทใหม่</span>}
                    </div>
                    <div className="rename-hint">ดับเบิลคลิกเพื่อเปลี่ยนชื่อ</div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Main area */}
        <div style={s.main}>
          {!currentMode ? (
            // Mode selector
            <div style={s.modeScreen}>
              <div>
                <p style={{ color: "#888", textAlign: "center", margin: "0 0 4px" }}>เลือกโหมด AI</p>
                <h2 style={s.modeTitle}>คุณต้องการทำอะไรวันนี้?</h2>
              </div>
              <div style={s.modeCards}>
                {Object.entries(MODE_LABELS).map(([key, info]) => (
                  <div
                    key={key}
                    style={s.modeCard(hoveredMode === key)}
                    onMouseEnter={() => setHoveredMode(key)}
                    onMouseLeave={() => setHoveredMode(null)}
                    onClick={() => pickMode(key)}
                  >
                    <div style={s.modeIcon}>{info.icon}</div>
                    <div style={s.modeName}>{info.th}</div>
                    <div style={s.modeDesc}>{info.desc}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <>
              {/* Chat header with mode toggle */}
              <div style={s.chatHeader}>
                <span style={s.chatHeaderTitle}>
                  {activeSession?.name || (pendingMode ? "แชทใหม่" : "แชท")}
                </span>
                {Object.entries(MODE_LABELS).map(([key, info]) => (
                  <div
                    key={key}
                    style={s.modePill(currentMode === key)}
                    onClick={() => activeSession ? switchMode(key) : setPendingMode(key)}
                  >
                    {info.icon} {info.th}
                  </div>
                ))}
              </div>

              {/* Chat thread */}
              <div style={s.messages}>
                {messages.length === 0 && (
                  <p style={{ color: "#aaa", textAlign: "center", margin: "auto" }}>
                    {MODE_LABELS[currentMode]?.icon} เริ่มต้นการสนทนากับ {MODE_LABELS[currentMode]?.th}
                  </p>
                )}
                {messages.map((msg, i) => (
                  <div key={i} style={s.bubble(msg.role)}>
                    {msg.role === "assistant" ? (
                      <div className="msg-content">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    ) : (
                      msg.content
                    )}
                  </div>
                ))}
                {sending && <TypingIndicator />}
                <div ref={bottomRef} />
              </div>
              <div style={s.inputRow}>
                <textarea
                  style={s.textarea}
                  rows={2}
                  placeholder="พิมพ์ข้อความ… (Enter ส่ง, Shift+Enter ขึ้นบรรทัดใหม่)"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKey}
                  disabled={sending}
                />
                <button style={s.sendBtn(sending || !input.trim())} onClick={sendMessage} disabled={sending || !input.trim()}>
                  ส่ง
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
