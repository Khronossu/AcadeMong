import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { t } from "../theme";

const MODE_LABELS = {
  dreamer:  { th: "Career Dreamer", icon: "🌟", desc: "สำรวจอาชีพและความสนใจ" },
  tcas_rag: { th: "TCAS Advisor",   icon: "🎓", desc: "ตรวจสอบสิทธิ์และเปรียบเทียบคณะ" },
};

function truncateName(text, max = 42) {
  if (!text) return null;
  const clean = text.trim();
  return clean.length <= max ? clean : clean.slice(0, max).trimEnd() + "…";
}

export default function ChatInterface({ getToken, sessions, setSessions, activeSession, setActiveSession, mobile }) {
  const [pendingMode, setPendingMode] = useState("dreamer");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);
  // Set to true when sendMessage creates a new session so the effect doesn't
  // overwrite the optimistically-rendered messages with the empty server response.
  const skipNextFetch = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  // Load messages when switching to an existing session
  useEffect(() => {
    if (!activeSession) { setMessages([]); return; }
    if (skipNextFetch.current) { skipNextFetch.current = false; return; }
    const controller = new AbortController();
    (async () => {
      try {
        const token = await getToken();
        if (controller.signal.aborted) return;
        const res = await fetch(`/api/chat/${activeSession.id}/messages`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!res.ok) return;
        const data = await res.json();
        setMessages(data.messages || []);
      } catch { /* graceful */ }
    })();
    return () => controller.abort();
  }, [activeSession?.id]);

  async function api(path, opts = {}) {
    const token = await getToken();
    const res = await fetch(path, {
      ...opts,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...opts.headers },
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }

  async function switchMode(mode) {
    if (!activeSession || mode === activeSession.ai_mode) return;
    try {
      await api(`/api/chat/${activeSession.id}/mode`, { method: "PATCH", body: JSON.stringify({ ai_mode: mode }) });
      const updated = { ...activeSession, ai_mode: mode };
      setActiveSession(updated);
      setSessions((p) => p.map((s) => s.id === updated.id ? updated : s));
    } catch { /* graceful */ }
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);

    let session = activeSession;

    // Lazy session creation on first message
    if (!session && pendingMode) {
      try {
        const data = await api("/api/chat/session", { method: "POST", body: JSON.stringify({ ai_mode: pendingMode }) });
        session = { id: data.session_id, ai_mode: data.ai_mode, name: null };
        skipNextFetch.current = true;
        setActiveSession(session);
        setSessions((p) => [session, ...p]);
        setPendingMode(null);
      } catch (e) { setSending(false); alert("ไม่สามารถสร้างเซสชันได้: " + e.message); return; }
    }

    if (!session) { setSending(false); return; }
    setMessages((p) => [...p, { role: "user", content: text }]);

    try {
      const data = await api(`/api/chat/${session.id}/message`, { method: "POST", body: JSON.stringify({ content: text }) });
      setMessages((p) => [...p, { role: data.role, content: data.content }]);

      // Auto-name from first message
      if (!session.name) {
        const name = truncateName(text);
        if (name) {
          await api(`/api/chat/${session.id}/name`, { method: "PATCH", body: JSON.stringify({ name }) });
          const named = { ...session, name };
          setActiveSession(named);
          setSessions((p) => p.map((s) => s.id === named.id ? named : s));
        }
      }
    } catch (e) {
      setMessages((p) => [...p, { role: "assistant", content: `⚠️ เกิดข้อผิดพลาด: ${e.message}` }]);
    } finally { setSending(false); }
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  }

  const currentMode = activeSession?.ai_mode || pendingMode;

  return (
    <>
      <style>{`
        @keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-5px)} }
        .msg-content p{margin:0 0 6px} .msg-content p:last-child{margin:0}
        .msg-content table{border-collapse:collapse;width:100%;margin:8px 0;font-size:17px}
        .msg-content th,.msg-content td{border:1px solid ${t.border};padding:7px 12px;text-align:left}
        .msg-content th{background:${t.card};font-weight:600;color:${t.text2}}
        .msg-content ul,.msg-content ol{margin:4px 0;padding-left:22px}
        .msg-content li{margin-bottom:4px}
        .msg-content strong{color:${t.accentHov}}
        .msg-content code{background:${t.card};border:1px solid ${t.border};padding:2px 7px;border-radius:4px;font-size:16px}
        .msg-content pre{background:${t.text1};color:#f0ebe2;padding:14px;border-radius:8px;overflow-x:auto;font-size:16px}
        .msg-content hr{border:none;border-top:1px solid ${t.border};margin:10px 0}
        .msg-content em{color:${t.text2}}
      `}</style>

      {/* ── Center chat ── */}
      <div style={s.center}>
        {/* Chat header */}
        <div style={{ ...s.chatHeader, ...(mobile ? { flexWrap: "wrap", padding: "8px 12px", gap: 6 } : {}) }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={s.chatTitle}>{activeSession?.name || "แชทใหม่"}</div>
            <div style={s.chatSub}>{MODE_LABELS[currentMode]?.th} · {messages.length} ข้อความ</div>
          </div>
          <div style={{ ...s.modeToggle, ...(mobile ? { width: "100%", flexShrink: 1 } : {}) }}>
            {Object.entries(MODE_LABELS).map(([key, info]) => (
              <button
                key={key}
                style={{ ...s.modeBtn, ...(currentMode === key ? s.modeBtnActive : {}), ...(mobile ? { flex: 1, textAlign: "center" } : {}) }}
                onClick={() => activeSession ? switchMode(key) : setPendingMode(key)}
              >
                {info.icon} {info.th}
              </button>
            ))}
          </div>
        </div>

        {/* Messages */}
        <div style={{ ...s.messages, ...(mobile ? { padding: "12px 16px" } : {}) }}>
          {messages.length === 0 && (
            <div style={s.emptyState}>
              <div style={s.emptyIcon}>{MODE_LABELS[currentMode]?.icon}</div>
              <div style={s.emptyText}>เริ่มต้นการสนทนากับ {MODE_LABELS[currentMode]?.th}</div>
              <div style={s.emptySub}>{MODE_LABELS[currentMode]?.desc}</div>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} style={{ ...s.msgRow, ...(msg.role === "user" ? s.msgRowUser : {}) }}>
              <div style={{ ...s.msgAvatar, ...(msg.role === "user" ? s.msgAvatarUser : s.msgAvatarAI) }}>
                {msg.role === "user" ? "P" : "A"}
              </div>
              <div style={{ ...s.bubble, ...(msg.role === "user" ? s.bubbleUser : s.bubbleAI), ...(mobile ? { maxWidth: "90%" } : {}) }}>
                {msg.role === "assistant"
                  ? <div className="msg-content"><ReactMarkdown>{msg.content}</ReactMarkdown></div>
                  : msg.content
                }
              </div>
            </div>
          ))}
          {sending && (
            <div style={s.msgRow}>
              <div style={{ ...s.msgAvatar, ...s.msgAvatarAI }}>A</div>
              <div style={{ ...s.bubble, ...s.bubbleAI, display: "flex", gap: 4, padding: "10px 14px" }}>
                {[0, 200, 400].map((d) => (
                  <span key={d} style={{ ...s.dot, animationDelay: `${d}ms` }} />
                ))}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{ ...s.inputRow, ...(mobile ? { padding: "8px 12px" } : {}) }}>
          <textarea
            style={s.textarea}
            rows={mobile ? 1 : 2}
            placeholder="พิมพ์ข้อความ…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            disabled={sending}
          />
          <button
            style={{ ...s.sendBtn, ...(sending || !input.trim() ? s.sendBtnDisabled : {}) }}
            onClick={sendMessage}
            disabled={sending || !input.trim()}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M22 2L11 13M22 2L15 22 11 13 2 9l20-7z" />
            </svg>
          </button>
        </div>
      </div>

      {/* ── Right context panel — hidden on mobile ── */}
      {!mobile && <RightPanel getToken={getToken} />}
    </>
  );
}

function RightPanel({ getToken }) {
  const [profile, setProfile] = useState(null);
  const [eligible, setEligible] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const token = await getToken();
        const res = await fetch("/api/profile/me", { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal });
        if (res.ok) setProfile(await res.json());
      } catch { /* graceful */ }
    })();
    return () => controller.abort();
  }, []);

  return (
    <div style={rp.panel}>
      {/* Profile summary */}
      <div style={rp.section}>
        <div style={rp.label}>โปรไฟล์</div>
        <div style={rp.card}>
          {profile ? (
            <>
              {profile.gpax != null && <div style={rp.row}><span style={rp.key}>GPAX</span><span style={rp.val}>{profile.gpax}</span></div>}
              {profile.current_school && <div style={rp.row}><span style={rp.key}>โรงเรียน</span><span style={{ ...rp.val, fontSize: 11 }}>{profile.current_school}</span></div>}
              {profile.test_scores?.slice(0, 4).map((s) => (
                <div key={s.subject + s.exam_year} style={rp.row}>
                  <span style={rp.key}>{s.subject}</span>
                  <span style={rp.val}>{s.score}</span>
                </div>
              ))}
              {!profile.gpax && !profile.test_scores?.length && (
                <div style={{ fontSize: 11, color: t.text3 }}>ยังไม่มีข้อมูล — กรอกในแท็บโปรไฟล์</div>
              )}
            </>
          ) : (
            <div style={{ fontSize: 11, color: t.text3 }}>กำลังโหลด...</div>
          )}
        </div>
      </div>

      {/* Quick links */}
      <div style={rp.section}>
        <div style={rp.label}>ลัด</div>
        <div style={rp.quickLinks}>
          {[
            { emoji: "✅", text: "ตรวจสอบสิทธิ์" },
            { emoji: "📌", text: "สาขาที่บันทึก" },
            { emoji: "💼", text: "อาชีพแนะนำ" },
          ].map(({ emoji, text }) => (
            <div key={text} style={rp.quickLink}>
              <span>{emoji}</span>
              <span style={{ fontSize: 12, color: t.text2 }}>{text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Tips */}
      <div style={rp.section}>
        <div style={rp.label}>เคล็ดลับ</div>
        <div style={rp.tipCard}>
          <div style={rp.tipText}>ใช้ <strong>AI 1 (Career Dreamer)</strong> เพื่อสำรวจอาชีพที่เหมาะกับคุณ</div>
        </div>
        <div style={rp.tipCard}>
          <div style={rp.tipText}>ใช้ <strong>AI 2 (TCAS Advisor)</strong> เพื่อเช็คสิทธิ์การสมัครจากข้อมูล SQL จริง</div>
        </div>
      </div>
    </div>
  );
}

const s = {
  center: { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: t.bg, minWidth: 0 },

  chatHeader: { padding: "12px 20px", borderBottom: `1px solid ${t.border}`, display: "flex", alignItems: "center", gap: 12, background: t.surface, flexShrink: 0 },
  chatTitle:  { fontSize: 19, fontWeight: 700, color: t.text1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  chatSub:    { fontSize: 14, color: t.text3, marginTop: 2 },
  modeToggle: { display: "flex", background: t.card, borderRadius: 8, padding: 3, border: `1px solid ${t.border}`, flexShrink: 0 },
  modeBtn:    { padding: "5px 14px", borderRadius: 6, fontSize: 13, cursor: "pointer", border: "none", background: "transparent", color: t.text3, fontFamily: "inherit", whiteSpace: "nowrap", transition: "all .12s" },
  modeBtnActive: { background: t.surface, color: t.accent, fontWeight: 600, boxShadow: "0 1px 3px rgba(0,0,0,.08)" },

  messages: { flex: 1, overflowY: "auto", padding: "20px 10%", display: "flex", flexDirection: "column", gap: 16 },
  emptyState: { margin: "auto", textAlign: "center", padding: 40 },
  emptyIcon:  { fontSize: 57, marginBottom: 14 },
  emptyText:  { fontSize: 22, fontWeight: 700, color: t.text2, marginBottom: 8 },
  emptySub:   { fontSize: 17, color: t.text3 },

  msgRow:     { display: "flex", gap: 10, alignItems: "flex-start" },
  msgRowUser: { flexDirection: "row-reverse" },
  msgAvatar:  { width: 30, height: 30, borderRadius: 7, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700 },
  msgAvatarAI:   { background: t.accent, color: "#fff" },
  msgAvatarUser: { background: t.borderMd, color: t.text1 },
  bubble:     { padding: "12px 16px", fontSize: 18, lineHeight: 1.7, borderRadius: 10, maxWidth: "78%" },
  bubbleAI:   { background: t.surface, border: `1px solid ${t.border}`, color: t.text1, borderRadius: "2px 10px 10px 10px" },
  bubbleUser: { background: t.accent, color: "#fff", borderRadius: "10px 2px 10px 10px" },
  dot:        { width: 8, height: 8, borderRadius: "50%", background: t.borderMd, display: "inline-block", animation: "bounce 1s infinite" },

  inputRow:  { padding: "12px 20px", borderTop: `1px solid ${t.border}`, background: t.surface, display: "flex", gap: 8, alignItems: "flex-end", flexShrink: 0 },
  textarea:  { flex: 1, background: t.card, border: `1.5px solid ${t.border}`, borderRadius: 10, padding: "10px 14px", resize: "none", fontSize: 18, color: t.text1, outline: "none", fontFamily: "inherit", lineHeight: 1.5, transition: "border-color .15s" },
  sendBtn:   { width: 42, height: 42, background: t.accent, border: "none", borderRadius: 10, cursor: "pointer", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, transition: "background .15s" },
  sendBtnDisabled: { background: t.borderMd, cursor: "default" },
};

const rp = {
  panel:  { width: t.rightW, flexShrink: 0, background: t.surface, borderLeft: `1px solid ${t.border}`, padding: 14, overflowY: "auto" },
  section: { marginBottom: 20 },
  label:  { fontSize: 10, textTransform: "uppercase", letterSpacing: ".8px", color: t.text3, fontWeight: 600, marginBottom: 10 },
  card:   { background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, padding: 10 },
  row:    { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0", borderBottom: `1px solid ${t.border}` },
  key:    { fontSize: 11, color: t.text3 },
  val:    { fontSize: 12, fontWeight: 600, color: t.text1 },
  quickLinks: { display: "flex", flexDirection: "column", gap: 2 },
  quickLink: { display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", borderRadius: 8, cursor: "pointer", fontSize: 12 },
  tipCard: { background: t.accentBg, border: `1px solid rgba(92,138,94,.2)`, borderRadius: 8, padding: "8px 10px", marginBottom: 6 },
  tipText: { fontSize: 11, color: t.text2, lineHeight: 1.6 },
};
