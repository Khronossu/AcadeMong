import { useState } from "react";
import ProfileForm from "./components/ProfileForm";
import EligibilityResults from "./components/EligibilityResults";

const TABS = [
  { key: "profile", label: "โปรไฟล์" },
  { key: "eligibility", label: "ตรวจสอบคุณสมบัติ" },
];

export default function App() {
  const [tab, setTab] = useState("profile");
  const [token, setToken] = useState(localStorage.getItem("academong_token") || "");
  const [tokenInput, setTokenInput] = useState("");
  const [profileSaved, setProfileSaved] = useState(false);

  function saveToken() {
    localStorage.setItem("academong_token", tokenInput);
    setToken(tokenInput);
    setTokenInput("");
  }

  function clearToken() {
    localStorage.removeItem("academong_token");
    setToken("");
  }

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <h1 style={styles.logo}>AcadeMong</h1>
        <p style={styles.tagline}>ระบบแนะนำมหาวิทยาลัยสำหรับนักเรียนไทย</p>
      </header>

      {/* Token input (dev auth) */}
      <div style={styles.authBar}>
        {token ? (
          <span style={styles.authOk}>
            ✓ มี token แล้ว&nbsp;
            <button onClick={clearToken} style={styles.smallBtn}>ออกจากระบบ</button>
          </span>
        ) : (
          <div style={styles.tokenRow}>
            <input
              style={styles.tokenInput}
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="วาง Firebase ID token เพื่อเข้าสู่ระบบ"
            />
            <button onClick={saveToken} disabled={!tokenInput} style={styles.smallBtn}>
              บันทึก token
            </button>
          </div>
        )}
      </div>

      {/* Tab bar */}
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

      {/* Tab content */}
      <main style={styles.main}>
        {tab === "profile" && (
          <ProfileForm
            token={token}
            onSaved={() => setProfileSaved(true)}
          />
        )}
        {tab === "eligibility" && (
          <>
            {profileSaved || token ? (
              <EligibilityResults token={token} />
            ) : (
              <p style={styles.hint}>บันทึกโปรไฟล์ก่อนตรวจสอบคุณสมบัติ</p>
            )}
          </>
        )}
      </main>
    </div>
  );
}

const styles = {
  app: { minHeight: "100vh", background: "#f5f7fa", fontFamily: "'Segoe UI', sans-serif" },
  header: {
    background: "#0f3460", color: "#fff", padding: "1.5rem 2rem",
    textAlign: "center",
  },
  logo: { margin: 0, fontSize: "1.8rem", letterSpacing: 1 },
  tagline: { margin: "0.25rem 0 0", opacity: 0.8, fontSize: "0.9rem" },
  authBar: {
    background: "#e8edf5", padding: "0.6rem 2rem", borderBottom: "1px solid #d0d8e8",
    display: "flex", alignItems: "center",
  },
  authOk: { fontSize: "0.85rem", color: "#080" },
  tokenRow: { display: "flex", gap: "0.5rem", alignItems: "center", width: "100%" },
  tokenInput: {
    flex: 1, padding: "0.35rem 0.6rem", border: "1px solid #bbb",
    borderRadius: 6, fontSize: "0.85rem",
  },
  smallBtn: {
    padding: "0.3rem 0.75rem", border: "1px solid #0f3460", borderRadius: 6,
    background: "#fff", cursor: "pointer", fontSize: "0.8rem", color: "#0f3460",
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
  hint: { color: "#888", textAlign: "center", marginTop: "2rem" },
};
