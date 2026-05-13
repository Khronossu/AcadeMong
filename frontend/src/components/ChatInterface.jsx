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

export default function ChatInterface({ getToken, sessions, setSessions, activeSession, setActiveSession }) {
  const [pendingMode, setPendingMode] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  // Load messages when session changes
  useEffect(() => {
    if (!activeSession) { setMessages([]); return; }
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
        .msg-content table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px}
        .msg-content th,.msg-content td{border:1px solid ${t.border};padding:6px 10px;text-align:left}
        .msg-content th{background:${t.card};font-weight:600;color:${t.text2}}
        .msg-content ul,.msg-content ol{margin:4px 0;padding-left:20px}
        .msg-content li{margin-bottom:3px}
        .msg-content strong{color:${t.accentHov}}
        .msg-content code{background:${t.card};border:1px solid ${t.border};padding:1px 5px;border-radius:4px;font-size:12.5px}
        .msg-content pre{background:${t.text1};color:#f0ebe2;padding:12px;border-radius:8px;overflow-x:auto;font-size:12.5px}
        .msg-content hr{border:none;border-top:1px solid ${t.border};margin:10px 0}
        .msg-content em{color:${t.text2}}
      `}</style>

      {/* ── Center chat ── */}
      <div style={s.center}>
        {!currentMode ? (
          // Mode picker
          <div style={s.modeScreen}>
            <div style={s.modeHero}>
              <div style={s.modeTitle}>คุณต้องการทำอะไรวันนี้?</div>
              <div style={s.modeSub}>เลือกโหมด AI ที่เหมาะกับความต้องการของคุณ</div>
            </div>
            <div style={s.modeCards}>
              {Object.entries(MODE_LABELS).map(([key, info]) => (
                <button key={key} style={s.modeCard} onClick={() => setPendingMode(key)}>
                  <div style={s.modeCardIcon}>{info.icon}</div>
                  <div style={s.modeCardName}>{info.th}</div>
                  <div style={s.modeCardDesc}>{info.desc}</div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {/* Chat header */}
            <div style={s.chatHeader}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={s.chatTitle}>{activeSession?.name || "แชทใหม่"}</div>
                <div style={s.chatSub}>{MODE_LABELS[currentMode]?.th} · {messages.length} ข้อความ</div>
              </div>
              <div style={s.modeToggle}>
                {Object.entries(MODE_LABELS).map(([key, info]) => (
                  <button
                    key={key}
                    style={{ ...s.modeBtn, ...(currentMode === key ? s.modeBtnActive : {}) }}
                    onClick={() => activeSession ? switchMode(key) : setPendingMode(key)}
                  >
                    {info.icon} {info.th}
                  </button>
                ))}
              </div>
            </div>

            {/* Messages */}
            <div style={s.messages}>
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
                  <div style={{ ...s.bubble, ...(msg.role === "user" ? s.bubbleUser : s.bubbleAI) }}>
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
            <div style={s.inputRow}>
              <textarea
                style={s.textarea}
                rows={2}
                placeholder="พิมพ์ข้อความ… (Enter ส่ง · Shift+Enter ขึ้นบรรทัด)"
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
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M22 2L11 13M22 2L15 22 11 13 2 9l20-7z" />
                </svg>
              </button>
            </div>
          </>
        )}
      </div>

      {/* ── Right context panel ── */}
      <RightPanel getToken={getToken} />
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
  center: { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: t.bg },

  modeScreen: { flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 24, padding: 40 },
  modeHero: { textAlign: "center" },
  modeTitle: { fontSize: 20, fontWeight: 700, color: t.text1, marginBottom: 6 },
  modeSub:   { fontSize: 13, color: t.text3 },
  modeCards: { display: "flex", gap: 14 },
  modeCard:  {
    width: 200, padding: "24px 20px", background: t.surface,
    border: `1.5px solid ${t.border}`, borderRadius: 14, cursor: "pointer",
    textAlign: "center", fontFamily: "inherit", transition: "all .15s",
    display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
  },
  modeCardIcon: { fontSize: 32, marginBottom: 4 },
  modeCardName: { fontSize: 14, fontWeight: 700, color: t.text1 },
  modeCardDesc: { fontSize: 12, color: t.text3, lineHeight: 1.5 },

  chatHeader: { padding: "10px 20px", borderBottom: `1px solid ${t.border}`, display: "flex", alignItems: "center", gap: 12, background: t.surface, flexShrink: 0 },
  chatTitle:  { fontSize: 13, fontWeight: 600, color: t.text1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  chatSub:    { fontSize: 11, color: t.text3, marginTop: 1 },
  modeToggle: { display: "flex", background: t.card, borderRadius: 8, padding: 3, border: `1px solid ${t.border}`, flexShrink: 0 },
  modeBtn:    { padding: "4px 12px", borderRadius: 6, fontSize: 11, cursor: "pointer", border: "none", background: "transparent", color: t.text3, fontFamily: "inherit", whiteSpace: "nowrap", transition: "all .12s" },
  modeBtnActive: { background: t.surface, color: t.accent, fontWeight: 600, boxShadow: "0 1px 3px rgba(0,0,0,.08)" },

  messages: { flex: 1, overflowY: "auto", padding: "20px", display: "flex", flexDirection: "column", gap: 14 },
  emptyState: { margin: "auto", textAlign: "center", padding: 40 },
  emptyIcon:  { fontSize: 36, marginBottom: 10 },
  emptyText:  { fontSize: 14, fontWeight: 600, color: t.text2, marginBottom: 4 },
  emptySub:   { fontSize: 12, color: t.text3 },

  msgRow:     { display: "flex", gap: 10, alignItems: "flex-start" },
  msgRowUser: { flexDirection: "row-reverse" },
  msgAvatar:  { width: 26, height: 26, borderRadius: 7, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700 },
  msgAvatarAI:   { background: t.accent, color: "#fff" },
  msgAvatarUser: { background: t.borderMd, color: t.text1 },
  bubble:     { padding: "10px 14px", fontSize: 13.5, lineHeight: 1.65, borderRadius: 10, maxWidth: "78%" },
  bubbleAI:   { background: t.surface, border: `1px solid ${t.border}`, color: t.text1, borderRadius: "2px 10px 10px 10px" },
  bubbleUser: { background: t.accent, color: "#fff", borderRadius: "10px 2px 10px 10px" },
  dot:        { width: 7, height: 7, borderRadius: "50%", background: t.borderMd, display: "inline-block", animation: "bounce 1s infinite" },

  inputRow:  { padding: "12px 20px", borderTop: `1px solid ${t.border}`, background: t.surface, display: "flex", gap: 8, alignItems: "flex-end", flexShrink: 0 },
  textarea:  { flex: 1, background: t.card, border: `1.5px solid ${t.border}`, borderRadius: 10, padding: "9px 13px", resize: "none", fontSize: 13.5, color: t.text1, outline: "none", fontFamily: "inherit", lineHeight: 1.5, transition: "border-color .15s" },
  sendBtn:   { width: 36, height: 36, background: t.accent, border: "none", borderRadius: 9, cursor: "pointer", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, transition: "background .15s" },
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
