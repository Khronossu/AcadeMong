import { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { t } from "../theme";

function SignInScreen({ onSignIn }) {
  return (
    <div style={s.screen}>
      <div style={s.card}>
        <div style={s.logoMark}>🎓</div>
        <h1 style={s.title}>AcadeMong</h1>
        <p style={s.sub}>ผู้ช่วย AI สำหรับการเลือกคณะและวางแผนอาชีพ</p>
        <button
          style={s.googleBtn}
          onClick={() => Promise.resolve(onSignIn()).catch((e) => console.error("signIn error:", e))}
        >
          <svg width="18" height="18" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          เข้าสู่ระบบด้วย Google
        </button>
        <p style={s.footer}>สำหรับนักเรียนไทยที่กำลังเตรียมสมัคร TCAS</p>
      </div>
    </div>
  );
}

function RegisterScreen({ onRegister, error }) {
  const [username, setUsername] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const handle = async (e) => {
    e.preventDefault(); setSubmitting(true);
    await onRegister(username.trim());
    setSubmitting(false);
  };
  return (
    <div style={s.screen}>
      <div style={s.card}>
        <div style={s.logoMark}>🎓</div>
        <h1 style={s.title}>ตั้งชื่อผู้ใช้</h1>
        <p style={s.sub}>เลือก username สำหรับบัญชีของคุณ</p>
        <form onSubmit={handle}>
          {error && <p style={s.err}>{error}</p>}
          <input
            style={s.input}
            placeholder="username (ตัวอักษร ตัวเลข _)"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            pattern="^[a-zA-Z0-9_]+$"
            minLength={3} maxLength={50} required
          />
          <button style={s.submitBtn} type="submit" disabled={submitting}>
            {submitting ? "กำลังสร้างบัญชี…" : "เริ่มใช้งาน"}
          </button>
        </form>
      </div>
    </div>
  );
}

function LoadingScreen() {
  return (
    <div style={s.screen}>
      <div style={{ ...s.card, textAlign: "center" }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>⏳</div>
        <p style={{ color: t.text3, fontSize: 14 }}>กำลังโหลด…</p>
      </div>
    </div>
  );
}

export default function AuthGate({ children }) {
  const { authState, signIn, register, registerError, username, signOut, getToken } = useAuth();
  if (authState === "loading")        return <LoadingScreen />;
  if (authState === "signed-out")     return <SignInScreen onSignIn={signIn} />;
  if (authState === "needs-register") return <RegisterScreen onRegister={register} error={registerError} />;
  return children({ getToken, username, signOut });
}

const s = {
  screen: {
    minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
    background: t.bg, fontFamily: "'Inter','Sarabun',sans-serif",
  },
  card: {
    background: t.surface, borderRadius: 16, padding: "44px 40px",
    textAlign: "center", maxWidth: 380, width: "100%",
    border: `1px solid ${t.border}`, boxShadow: "0 4px 24px rgba(0,0,0,.06)",
  },
  logoMark: { fontSize: 40, marginBottom: 12 },
  title:    { fontSize: 26, fontWeight: 800, color: t.text1, margin: "0 0 6px", letterSpacing: "-.5px" },
  sub:      { color: t.text3, marginBottom: 28, fontSize: 14, lineHeight: 1.5 },
  googleBtn: {
    display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
    width: "100%", padding: "11px 0", border: `1.5px solid ${t.border}`,
    borderRadius: 10, background: t.surface, cursor: "pointer", fontSize: 14,
    fontWeight: 600, color: t.text1, fontFamily: "inherit", marginBottom: 16,
  },
  input: {
    width: "100%", padding: "10px 12px", border: `1.5px solid ${t.border}`,
    borderRadius: 10, fontSize: 14, marginBottom: 12, boxSizing: "border-box",
    fontFamily: "inherit", color: t.text1, outline: "none", background: t.card,
  },
  submitBtn: {
    width: "100%", padding: "11px 0", background: t.accent, color: "#fff",
    border: "none", borderRadius: 10, fontSize: 14, fontWeight: 600,
    cursor: "pointer", fontFamily: "inherit",
  },
  err:    { color: t.fail, fontSize: 13, marginBottom: 10 },
  footer: { fontSize: 11, color: t.text3, marginTop: 4 },
};
