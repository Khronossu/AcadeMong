import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";

const MODE_LABELS = {
  dreamer:  { th: "Career Dreamer",  desc: "สำรวจความสนใจและวางแผนอาชีพ", icon: "🌟" },
  tcas_rag: { th: "TCAS Advisor",    desc: "ตรวจสอบสิทธิ์และเปรียบเทียบคณะ",  icon: "🎓" },
};

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
  }),
  sessionMode: { fontSize: 11, color: "#aaa", textTransform: "uppercase", letterSpacing: .5 },
  sessionId: { fontSize: 12, color: "#ccc", marginTop: 2, fontFamily: "monospace" },

  main: { flex: 1, display: "flex", flexDirection: "column" },

  // Mode selector
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

  // Chat thread
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
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [hoveredMode, setHoveredMode] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => { loadSessions(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, sending]);

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
    try {
      const data = await api(`/api/chat/${session.id}/messages`);
      setMessages(data.messages || []);
    } catch { setMessages([]); }
  }

  async function startNewSession(mode) {
    try {
      const data = await api("/api/chat/session", {
        method: "POST",
        body: JSON.stringify({ ai_mode: mode }),
      });
      const newSession = { id: data.session_id, ai_mode: data.ai_mode };
      setSessions((prev) => [newSession, ...prev]);
      setActiveSession(newSession);
      setMessages([]);
    } catch (e) { alert("ไม่สามารถสร้างเซสชันได้: " + e.message); }
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || !activeSession || sending) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setSending(true);
    try {
      const data = await api(`/api/chat/${activeSession.id}/message`, {
        method: "POST",
        body: JSON.stringify({ content: text }),
      });
      setMessages((prev) => [...prev, { role: data.role, content: data.content }]);
    } catch (e) {
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ เกิดข้อผิดพลาด: ${e.message}` }]);
    } finally { setSending(false); }
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  }

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
      `}</style>

      <div style={s.container}>
        {/* Sidebar */}
        <div style={s.sidebar}>
          <div style={s.sidebarHeader}>
            <button style={s.newChatBtn} onClick={() => { setActiveSession(null); setMessages([]); }}>
              + แชทใหม่
            </button>
          </div>
          <div style={s.sessionList}>
            {sessions.map((sess) => (
              <div
                key={sess.id}
                style={s.sessionItem(activeSession?.id === sess.id)}
                onClick={() => selectSession(sess)}
              >
                <div style={s.sessionMode}>{MODE_LABELS[sess.ai_mode]?.th || sess.ai_mode}</div>
                <div style={s.sessionId}>{sess.id.slice(0, 8)}…</div>
              </div>
            ))}
          </div>
        </div>

        {/* Main area */}
        <div style={s.main}>
          {!activeSession ? (
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
                    onClick={() => startNewSession(key)}
                  >
                    <div style={s.modeIcon}>{info.icon}</div>
                    <div style={s.modeName}>{info.th}</div>
                    <div style={s.modeDesc}>{info.desc}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            // Chat thread
            <>
              <div style={s.messages}>
                {messages.length === 0 && (
                  <p style={{ color: "#aaa", textAlign: "center", margin: "auto" }}>
                    {MODE_LABELS[activeSession.ai_mode]?.icon} เริ่มต้นการสนทนากับ{" "}
                    {MODE_LABELS[activeSession.ai_mode]?.th}
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
