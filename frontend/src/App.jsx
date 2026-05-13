import { useState, useEffect, useCallback } from "react";
import AuthGate from "./components/AuthGate";
import ProfileForm from "./components/ProfileForm";
import EligibilityResults from "./components/EligibilityResults";
import ChatInterface from "./components/ChatInterface";
import CareerPathView from "./components/CareerPathView";
import SavedMajorsView from "./components/SavedMajorsView";
import ErrorBoundary from "./components/ErrorBoundary";
import { t } from "./theme";

const NAV = [
  { key: "chat",        icon: "💬", label: "แชทกับ AI" },
  { key: "profile",     icon: "👤", label: "โปรไฟล์" },
  { key: "eligibility", icon: "✅", label: "ตรวจสอบคุณสมบัติ" },
  { key: "saved",       icon: "📌", label: "สาขาที่บันทึก" },
  { key: "careers",     icon: "💼", label: "อาชีพแนะนำ" },
];

function AppContent({ getToken, username, signOut }) {
  const [tab, setTab] = useState("chat");
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);

  const api = useCallback(async (path, opts = {}) => {
    const token = await getToken();
    const res = await fetch(path, {
      ...opts,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...opts.headers },
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }, [getToken]);

  useEffect(() => {
    api("/api/chat/sessions")
      .then((d) => setSessions(d.sessions || []))
      .catch(() => {});
  }, []);

  function handleNewChat() {
    setActiveSession(null);
    setTab("chat");
  }

  return (
    <div style={s.app}>
      {/* ── Left sidebar ── */}
      <aside style={s.sidebar}>
        {/* Logo */}
        <div style={s.logoRow}>
          <div style={s.logoMark}>🎓</div>
          <div>
            <div style={s.logoName}>AcadeMong</div>
            <div style={s.logoSub}>AI Advisor</div>
          </div>
        </div>

        {/* Nav */}
        <div style={s.navSection}>
          {NAV.map(({ key, icon, label }) => (
            <button
              key={key}
              style={{ ...s.navItem, ...(tab === key ? s.navActive : {}) }}
              onClick={() => setTab(key)}
            >
              <span style={s.navIcon}>{icon}</span>
              <span style={s.navLabel}>{label}</span>
            </button>
          ))}
        </div>

        {/* Session list — only shown on chat tab */}
        {tab === "chat" && (
          <div style={s.sessionSection}>
            <div style={s.sectionLabel}>การสนทนา</div>
            <button style={s.newChatBtn} onClick={handleNewChat}>+ แชทใหม่</button>
            <div style={s.sessionList}>
              {sessions.map((sess) => (
                <SessionEntry
                  key={sess.id}
                  sess={sess}
                  active={activeSession?.id === sess.id}
                  onSelect={() => setActiveSession(sess)}
                  onDelete={async () => {
                    try {
                      await api(`/api/chat/${sess.id}`, { method: "DELETE" });
                      setSessions((p) => p.filter((s) => s.id !== sess.id));
                      if (activeSession?.id === sess.id) setActiveSession(null);
                    } catch { /* graceful */ }
                  }}
                  onRename={async (name) => {
                    try {
                      await api(`/api/chat/${sess.id}/name`, { method: "PATCH", body: JSON.stringify({ name }) });
                      setSessions((p) => p.map((s) => s.id === sess.id ? { ...s, name } : s));
                      if (activeSession?.id === sess.id) setActiveSession((s) => ({ ...s, name }));
                    } catch { /* graceful */ }
                  }}
                />
              ))}
            </div>
          </div>
        )}

        {/* User row */}
        <div style={s.userRow}>
          <div style={s.avatar}>{username?.[0]?.toUpperCase() ?? "?"}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={s.userName}>{username}</div>
            <div style={s.userRole}>นักเรียน</div>
          </div>
          <button style={s.signOutBtn} onClick={signOut} title="ออกจากระบบ">↩</button>
        </div>
      </aside>

      {/* ── Main area ── */}
      <div style={s.mainWrap}>
        {/* Keep all tabs mounted — visibility toggled via display */}
        <div style={{ display: tab === "chat" ? "flex" : "none", flex: 1, overflow: "hidden", height: "100%" }}>
          <ErrorBoundary>
            <ChatInterface
              getToken={getToken}
              sessions={sessions}
              setSessions={setSessions}
              activeSession={activeSession}
              setActiveSession={setActiveSession}
            />
          </ErrorBoundary>
        </div>
        <div style={{ display: tab === "profile" ? "block" : "none", flex: 1, overflow: "auto", height: "100%", background: t.bg }}>
          <ErrorBoundary><ProfileForm getToken={getToken} /></ErrorBoundary>
        </div>
        <div style={{ display: tab === "eligibility" ? "block" : "none", flex: 1, overflow: "auto", height: "100%", background: t.bg }}>
          <ErrorBoundary><EligibilityResults getToken={getToken} /></ErrorBoundary>
        </div>
        <div style={{ display: tab === "saved" ? "block" : "none", flex: 1, overflow: "auto", height: "100%", background: t.bg }}>
          <ErrorBoundary><SavedMajorsView getToken={getToken} /></ErrorBoundary>
        </div>
        <div style={{ display: tab === "careers" ? "block" : "none", flex: 1, overflow: "auto", height: "100%", background: t.bg }}>
          <ErrorBoundary><CareerPathView getToken={getToken} /></ErrorBoundary>
        </div>
      </div>
    </div>
  );
}

function SessionEntry({ sess, active, onSelect, onDelete, onRename }) {
  const [renaming, setRenaming] = useState(false);
  const [val, setVal] = useState(sess.name || "");
  const [hovered, setHovered] = useState(false);

  return (
    <div
      style={{ ...s.sessItem, ...(active ? s.sessActive : {}) }}
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div style={s.sessDot} />
      {renaming ? (
        <input
          autoFocus
          style={s.sessInput}
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onBlur={() => { setRenaming(false); onRename(val.trim() || null); }}
          onKeyDown={(e) => {
            if (e.key === "Enter") { setRenaming(false); onRename(val.trim() || null); }
            if (e.key === "Escape") setRenaming(false);
          }}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span
          style={s.sessName}
          onDoubleClick={(e) => { e.stopPropagation(); setRenaming(true); setVal(sess.name || ""); }}
        >
          {sess.name || <em style={{ color: t.text3 }}>แชทใหม่</em>}
        </span>
      )}
      {hovered && !renaming && (
        <button
          style={s.sessDelete}
          onClick={(e) => { e.stopPropagation(); if (confirm("ลบแชทนี้?")) onDelete(); }}
        >×</button>
      )}
    </div>
  );
}

export default function App() {
  return (
    <AuthGate>
      {(props) => <AppContent {...props} />}
    </AuthGate>
  );
}

const s = {
  app: { display: "flex", height: "100vh", overflow: "hidden", fontFamily: "'Inter','Sarabun',sans-serif", background: t.bg },

  // Sidebar
  sidebar: {
    width: t.sidebarW, flexShrink: 0, background: t.surface,
    borderRight: `1px solid ${t.border}`, display: "flex",
    flexDirection: "column", height: "100%", overflow: "hidden",
  },
  logoRow: { padding: "14px 16px", borderBottom: `1px solid ${t.border}`, display: "flex", alignItems: "center", gap: 10, flexShrink: 0 },
  logoMark: { width: 30, height: 30, background: t.accent, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, flexShrink: 0 },
  logoName: { fontSize: 15, fontWeight: 700, color: t.text1, letterSpacing: "-.3px" },
  logoSub:  { fontSize: 10, color: t.text3 },

  navSection: { padding: "10px 0", flexShrink: 0 },
  navItem: {
    display: "flex", alignItems: "center", gap: 9, width: "100%",
    padding: "7px 14px", fontSize: 13, color: t.text2,
    background: "transparent", border: "none", borderLeft: "2px solid transparent",
    cursor: "pointer", fontFamily: "inherit", textAlign: "left", transition: "all .12s",
  },
  navActive: { color: t.accent, borderLeftColor: t.accent, background: t.accentLight, fontWeight: 500 },
  navIcon:  { fontSize: 13, width: 18, textAlign: "center" },
  navLabel: { fontSize: 13 },

  sessionSection: { display: "flex", flexDirection: "column", flex: 1, overflow: "hidden", padding: "8px 0" },
  sectionLabel: { fontSize: 10, textTransform: "uppercase", letterSpacing: ".8px", color: t.text3, fontWeight: 600, padding: "0 14px 6px" },
  newChatBtn: {
    margin: "0 10px 6px", padding: "6px 12px", background: "transparent",
    border: `1px dashed ${t.borderMd}`, borderRadius: 8, fontSize: 12,
    color: t.text3, cursor: "pointer", fontFamily: "inherit", textAlign: "left",
    transition: "all .12s",
  },
  sessionList: { flex: 1, overflowY: "auto" },

  sessItem: {
    display: "flex", alignItems: "center", gap: 7, padding: "6px 14px",
    fontSize: 12, color: t.text3, cursor: "pointer",
    borderLeft: "2px solid transparent", position: "relative",
  },
  sessActive: { color: t.text2, borderLeftColor: t.borderMd, background: t.card, fontWeight: 500 },
  sessDot: { width: 5, height: 5, borderRadius: "50%", background: t.borderMd, flexShrink: 0 },
  sessName: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 12 },
  sessDelete: { background: "none", border: "none", color: t.text3, cursor: "pointer", fontSize: 14, padding: "0 2px", lineHeight: 1 },
  sessInput: { flex: 1, background: t.card, border: `1px solid ${t.accent}`, borderRadius: 4, color: t.text1, fontSize: 12, padding: "1px 5px", outline: "none", fontFamily: "inherit" },

  userRow: {
    marginTop: "auto", padding: "10px 12px", borderTop: `1px solid ${t.border}`,
    display: "flex", alignItems: "center", gap: 9, flexShrink: 0,
  },
  avatar: { width: 28, height: 28, borderRadius: "50%", background: t.accent, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0 },
  userName: { fontSize: 12, fontWeight: 500, color: t.text1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  userRole: { fontSize: 10, color: t.text3 },
  signOutBtn: { background: "none", border: "none", color: t.text3, cursor: "pointer", fontSize: 14, padding: "2px 4px", flexShrink: 0 },

  mainWrap: { flex: 1, display: "flex", overflow: "hidden", height: "100%" },
};
