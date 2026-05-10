import { useState } from "react";
import AuthGate from "./components/AuthGate";
import ProfileForm from "./components/ProfileForm";
import EligibilityResults from "./components/EligibilityResults";
import ChatInterface from "./components/ChatInterface";

const TABS = [
  { key: "chat",        label: "แชทกับ AI" },
  { key: "profile",     label: "โปรไฟล์" },
  { key: "eligibility", label: "ตรวจสอบคุณสมบัติ" },
];

function AppContent({ getToken, username, signOut }) {
  const [tab, setTab] = useState("chat");
  const [profileSaved, setProfileSaved] = useState(false);

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <div style={styles.headerInner}>
          <div>
            <h1 style={styles.logo}>AcadeMong</h1>
            <p style={styles.tagline}>ระบบแนะนำมหาวิทยาลัยสำหรับนักเรียนไทย</p>
          </div>
          <div style={styles.userBar}>
            <span style={styles.usernameLabel}>@{username}</span>
            <button onClick={signOut} style={styles.signOutBtn}>ออกจากระบบ</button>
          </div>
        </div>
      </header>

      <nav style={styles.tabBar}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{ ...styles.tab, ...(tab === t.key ? styles.tabActive : {}) }}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main style={tab === "chat" ? styles.mainFull : styles.main}>
        {tab === "chat" && <ChatInterface getToken={getToken} />}
        {tab === "profile" && (
          <ProfileForm getToken={getToken} onSaved={() => setProfileSaved(true)} />
        )}
        {tab === "eligibility" && (
          profileSaved
            ? <EligibilityResults getToken={getToken} />
            : <EligibilityResults getToken={getToken} />
        )}
      </main>
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

const styles = {
  app: { minHeight: "100vh", background: "#f5f7fa", fontFamily: "Sarabun, 'Segoe UI', sans-serif" },
  header: { background: "#0f3460", color: "#fff", padding: "1rem 2rem" },
  headerInner: { display: "flex", alignItems: "center", justifyContent: "space-between" },
  logo: { margin: 0, fontSize: "1.6rem", letterSpacing: 1 },
  tagline: { margin: "0.2rem 0 0", opacity: 0.75, fontSize: "0.85rem" },
  userBar: { display: "flex", alignItems: "center", gap: 12 },
  usernameLabel: { fontSize: 14, opacity: 0.85 },
  signOutBtn: {
    padding: "6px 14px", border: "1.5px solid rgba(255,255,255,.4)", borderRadius: 8,
    background: "transparent", color: "#fff", cursor: "pointer", fontSize: 13,
  },
  tabBar: {
    display: "flex", background: "#fff", borderBottom: "2px solid #e0e6f0",
    padding: "0 2rem", gap: "0.5rem",
  },
  tab: {
    background: "none", border: "none", borderBottom: "3px solid transparent",
    padding: "0.75rem 1.25rem", cursor: "pointer", fontSize: "0.95rem",
    color: "#555", marginBottom: "-2px",
  },
  tabActive: { borderBottomColor: "#0f3460", color: "#0f3460", fontWeight: 600 },
  main: { padding: "1.5rem 2rem", maxWidth: 900, margin: "0 auto" },
  mainFull: { padding: "1rem 2rem" },
};
