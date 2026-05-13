import { useState, useEffect, useCallback } from "react";
import AuthGate from "./components/AuthGate";
import ProfileForm from "./components/ProfileForm";
import EligibilityResults from "./components/EligibilityResults";
import ChatInterface from "./components/ChatInterface";
import CareerPathView from "./components/CareerPathView";
import SavedMajorsView from "./components/SavedMajorsView";
import ErrorBoundary from "./components/ErrorBoundary";
import ConfirmDialog from "./components/ConfirmDialog";
import { t } from "./theme";
import { useWindowSize, isMobile } from "./hooks/useWindowSize";
import Icon from "./components/Icon";

const NAV = [
  { key: "chat",        iconName: "chat",          label: "แชท" },
  { key: "profile",     iconName: "person",         label: "โปรไฟล์" },
  { key: "eligibility", iconName: "check-circle",   label: "คุณสมบัติ" },
  { key: "saved",       iconName: "bookmark",       label: "บันทึก" },
  { key: "careers",     iconName: "briefcase",      label: "อาชีพ" },
];

function AppContent({ getToken, username, signOut }) {
  const [tab, setTab] = useState("chat");
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { w } = useWindowSize();
  const mobile = isMobile(w);

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

  // Close sidebar on tab change (mobile)
  useEffect(() => { setSidebarOpen(false); }, [tab]);

  const sidebar = (
    <aside style={{ ...s.sidebar, ...(mobile ? s.sidebarMobile : {}), ...(mobile && !sidebarOpen ? s.sidebarHidden : {}) }}>
      <div style={s.logoRow}>
        <div style={s.logoMark}><Icon name="graduation" size={20} color="#fff" /></div>
        <div>
          <div style={s.logoName}>AcadeMong</div>
          <div style={s.logoSub}>AI Advisor</div>
        </div>
        {mobile && (
          <button style={s.closeBtn} onClick={() => setSidebarOpen(false)}>✕</button>
        )}
      </div>

      <div style={s.navSection}>
        {NAV.map(({ key, iconName, label }) => (
          <button
            key={key}
            style={{ ...s.navItem, ...(tab === key ? s.navActive : {}) }}
            onClick={() => { setTab(key); if (mobile) setSidebarOpen(false); }}
          >
            <span style={s.navIcon}><Icon name={iconName} size={16} /></span>
            <span style={s.navLabel}>{label}</span>
          </button>
        ))}
        <div style={s.navDivider} />
        <button style={s.navItem} onClick={() => { setTab("settings"); if (mobile) setSidebarOpen(false); }}>
          <span style={s.navIcon}><Icon name="gear" size={16} /></span>
          <span style={s.navLabel}>ตั้งค่า</span>
        </button>
      </div>

      {tab === "chat" && (
        <div style={s.sessionSection}>
          <div style={s.sectionLabel}>การสนทนา</div>
          <button style={s.newChatBtn} onClick={() => { setActiveSession(null); if (mobile) setSidebarOpen(false); }}>
            + แชทใหม่
          </button>
          <div style={s.sessionList}>
            {sessions.map((sess) => (
              <SessionEntry
                key={sess.id}
                sess={sess}
                active={activeSession?.id === sess.id}
                onSelect={() => { setActiveSession(sess); if (mobile) setSidebarOpen(false); }}
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

      <div style={s.userRow}>
        <div style={s.avatar}>{username?.[0]?.toUpperCase() ?? "?"}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={s.userName}>{username}</div>
          <div style={s.userRole}>นักเรียน</div>
        </div>
        <button style={s.signOutBtn} onClick={signOut} title="ออกจากระบบ">↩</button>
      </div>
    </aside>
  );

  return (
    <div style={s.app}>
      {/* Mobile overlay */}
      {mobile && sidebarOpen && (
        <div style={s.overlay} onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar — desktop always visible, mobile slide-in */}
      {sidebar}

      {/* Main */}
      <div style={s.mainWrap}>
        {/* Mobile top bar */}
        {mobile && (
          <div style={s.mobileTopBar}>
            <button style={s.hamburger} onClick={() => setSidebarOpen(true)}>☰</button>
            <div style={s.mobileTitle}>
              <Icon name={NAV.find((n) => n.key === tab)?.iconName} size={20} /> {NAV.find((n) => n.key === tab)?.label}
            </div>
            <div style={{ width: 36 }} />
          </div>
        )}

        {/* Tab content — flex:1 + minHeight:0 so the column flex shrinks correctly */}
        <div style={{ display: tab === "chat" ? "flex" : "none", flex: 1, minHeight: 0, overflow: "hidden" }}>
          <ErrorBoundary>
            <ChatInterface
              getToken={getToken}
              sessions={sessions}
              setSessions={setSessions}
              activeSession={activeSession}
              setActiveSession={setActiveSession}
              mobile={mobile}
            />
          </ErrorBoundary>
        </div>
        {[
          { key: "profile",     C: ProfileForm },
          { key: "eligibility", C: EligibilityResults },
          { key: "saved",       C: SavedMajorsView },
          { key: "careers",     C: CareerPathView },
        ].map(({ key, C }) => (
          <div key={key} style={{ display: tab === key ? "flex" : "none", flex: 1, minHeight: 0, overflow: "auto", flexDirection: "column", background: t.bg }}>
            <ErrorBoundary><C getToken={getToken} /></ErrorBoundary>
          </div>
        ))}
        {tab === "settings" && (
          <div style={{ flex: 1, minHeight: 0, overflow: "auto", background: t.bg }}>
            <ErrorBoundary><SettingsPage /></ErrorBoundary>
          </div>
        )}

        {/* Bottom tab nav — inside mainWrap so it stacks at the bottom of the column */}
        {mobile && (
          <nav style={s.bottomNav}>
            {NAV.map(({ key, iconName, label }) => (
              <button
                key={key}
                style={{ ...s.bottomNavItem, ...(tab === key ? s.bottomNavActive : {}) }}
                onClick={() => setTab(key)}
              >
                <Icon name={iconName} size={26} />
                <span style={{ fontSize: 13, marginTop: 2 }}>{label}</span>
              </button>
            ))}
          </nav>
        )}
      </div>
    </div>
  );
}

function SettingsPage() {
  return (
    <div style={{ maxWidth: 600, margin: "0 auto", padding: "1.5rem 2rem", fontFamily: "'Inter','Sarabun',sans-serif" }}>
      <h2 style={{ color: t.text1, fontSize: 22, fontWeight: 700, marginBottom: "1.5rem" }}>ตั้งค่า</h2>
      <div style={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 12, padding: "1.25rem" }}>
        <div style={{ fontSize: 17, fontWeight: 600, color: t.text1, marginBottom: 4 }}>ภาษา / Language</div>
        <div style={{ fontSize: 15, color: t.text3, marginBottom: 12 }}>เลือกภาษาที่ใช้แสดงผล UI</div>
        <div style={{ display: "flex", gap: 8 }}>
          {["ภาษาไทย", "English"].map((lang) => (
            <button key={lang} style={{
              padding: "7px 18px", border: `1.5px solid ${lang === "ภาษาไทย" ? t.accent : t.border}`,
              borderRadius: 20, background: lang === "ภาษาไทย" ? t.accentBg : t.surface,
              color: lang === "ภาษาไทย" ? t.accent : t.text2, fontSize: 15,
              cursor: "pointer", fontFamily: "inherit", fontWeight: lang === "ภาษาไทย" ? 600 : 400,
            }}>{lang}</button>
          ))}
        </div>
        <div style={{ fontSize: 13, color: t.text3, marginTop: 8 }}>* การเปลี่ยนภาษา English จะพร้อมใช้งานในอนาคต</div>
      </div>
    </div>
  );
}

function SessionEntry({ sess, active, onSelect, onDelete, onRename }) {
  const [renaming, setRenaming] = useState(false);
  const [val, setVal] = useState(sess.name || "");
  const [hovered, setHovered] = useState(false);
  const [confirming, setConfirming] = useState(false);

  return (
    <>
      {confirming && (
        <ConfirmDialog
          message={`ลบ "${sess.name || "แชทใหม่"}" ?`}
          confirmLabel="ลบแชท"
          onConfirm={() => { setConfirming(false); onDelete(); }}
          onCancel={() => setConfirming(false)}
        />
      )}
      <div
        style={{ ...s.sessItem, ...(active ? s.sessActive : {}) }}
        onClick={onSelect}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <div style={{ ...s.sessDot, ...(active ? { background: t.accent } : {}) }} />
        {renaming ? (
          <input
            autoFocus style={s.sessInput}
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
          <span style={s.sessName} onDoubleClick={(e) => { e.stopPropagation(); setRenaming(true); setVal(sess.name || ""); }}>
            {sess.name || <em style={{ color: t.text3 }}>แชทใหม่</em>}
          </span>
        )}
        {hovered && !renaming && (
          <button style={s.sessDelete} onClick={(e) => { e.stopPropagation(); setConfirming(true); }}>×</button>
        )}
      </div>
    </>
  );
}

export default function App() {
  return <AuthGate>{(props) => <AppContent {...props} />}</AuthGate>;
}

const s = {
  app: { display: "flex", height: "100dvh", overflow: "hidden", fontFamily: "'Inter','Sarabun',sans-serif", background: t.bg, position: "relative" },

  overlay: { position: "fixed", inset: 0, background: "rgba(0,0,0,.4)", zIndex: 99 },

  sidebar: {
    width: "220px", flexShrink: 0, background: t.surface,
    borderRight: `1px solid ${t.border}`, display: "flex",
    flexDirection: "column", height: "100%", overflow: "hidden", zIndex: 100,
  },
  sidebarMobile: {
    position: "fixed", top: 0, left: 0, bottom: 0,
    boxShadow: "4px 0 24px rgba(0,0,0,.12)", transition: "transform .25s ease",
  },
  sidebarHidden: { transform: "translateX(-100%)" },

  logoRow: { padding: "14px 16px", borderBottom: `1px solid ${t.border}`, display: "flex", alignItems: "center", gap: 10, flexShrink: 0 },
  logoMark: { width: 34, height: 34, background: t.accent, borderRadius: 9, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, flexShrink: 0 },
  logoName: { fontSize: 22, fontWeight: 800, color: t.text1, letterSpacing: "-.4px" },
  logoSub:  { fontSize: 13, color: t.text3 },
  closeBtn: { marginLeft: "auto", background: "none", border: "none", color: t.text3, cursor: "pointer", fontSize: 22, padding: 4 },

  navSection: { padding: "10px 0", flexShrink: 0 },
  navItem: {
    display: "flex", alignItems: "center", gap: 10, width: "100%",
    padding: "10px 14px", fontSize: 16, color: t.text2,
    background: "transparent", border: "none", borderLeft: "2px solid transparent",
    cursor: "pointer", fontFamily: "inherit", textAlign: "left", transition: "all .12s",
  },
  navActive: { color: t.accent, borderLeftColor: t.accent, background: t.accentLight, fontWeight: 600 },
  navIcon:   { fontSize: 16, width: 22, textAlign: "center" },
  navLabel:  { fontSize: 16 },
  navDivider: { height: 1, background: t.border, margin: "6px 14px" },

  sessionSection: { display: "flex", flexDirection: "column", flex: 1, overflow: "hidden", padding: "8px 0" },
  sectionLabel: { fontSize: 12, textTransform: "uppercase", letterSpacing: ".8px", color: t.text3, fontWeight: 600, padding: "0 14px 6px" },
  newChatBtn: { margin: "0 10px 6px", padding: "8px 12px", background: "transparent", border: `1px dashed ${t.borderMd}`, borderRadius: 8, fontSize: 15, color: t.text3, cursor: "pointer", fontFamily: "inherit", textAlign: "left" },
  sessionList: { flex: 1, overflowY: "auto" },
  sessItem: { display: "flex", alignItems: "center", gap: 7, padding: "8px 14px", fontSize: 15, color: t.text3, cursor: "pointer", borderLeft: "2px solid transparent", position: "relative" },
  sessActive: { color: t.text2, borderLeftColor: t.borderMd, background: t.card, fontWeight: 500 },
  sessDot: { width: 6, height: 6, borderRadius: "50%", background: t.borderMd, flexShrink: 0 },
  sessName: { flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 15 },
  sessDelete: { background: "none", border: "none", color: t.text3, cursor: "pointer", fontSize: 18, padding: "0 2px", lineHeight: 1 },
  sessInput: { flex: 1, background: t.card, border: `1px solid ${t.accent}`, borderRadius: 4, color: t.text1, fontSize: 15, padding: "1px 5px", outline: "none", fontFamily: "inherit" },

  userRow: { marginTop: "auto", padding: "10px 12px", borderTop: `1px solid ${t.border}`, display: "flex", alignItems: "center", gap: 9, flexShrink: 0 },
  avatar: { width: 34, height: 34, borderRadius: "50%", background: t.accent, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, fontWeight: 700, flexShrink: 0 },
  userName: { fontSize: 15, fontWeight: 600, color: t.text1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  userRole: { fontSize: 12, color: t.text3 },
  signOutBtn: { background: "none", border: "none", color: t.text3, cursor: "pointer", fontSize: 18, padding: "2px 4px", flexShrink: 0 },

  mainWrap: { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 0 },

  mobileTopBar: { height: 56, background: t.surface, borderBottom: `1px solid ${t.border}`, display: "flex", alignItems: "center", padding: "0 12px", gap: 10, flexShrink: 0, zIndex: 10 },
  hamburger: { width: 40, height: 40, background: "none", border: "none", fontSize: 24, cursor: "pointer", color: t.text1, display: "flex", alignItems: "center", justifyContent: "center" },
  mobileTitle: { flex: 1, textAlign: "center", fontSize: 20, fontWeight: 700, color: t.text1 },

  bottomNav: { height: 64, background: t.surface, borderTop: `1px solid ${t.border}`, display: "flex", flexShrink: 0, zIndex: 100 },
  bottomNavItem: { flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 2, background: "none", border: "none", cursor: "pointer", color: t.text3, fontFamily: "inherit", padding: 0 },
  bottomNavActive: { color: t.accent },
};
