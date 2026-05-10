import { useState } from "react";
import { useAuth } from "../hooks/useAuth";

const s = {
  screen: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#0f3460",
    fontFamily: "Sarabun, sans-serif",
  },
  card: {
    background: "#fff",
    borderRadius: 16,
    padding: "48px 40px",
    textAlign: "center",
    maxWidth: 380,
    width: "100%",
    boxShadow: "0 8px 32px rgba(0,0,0,0.24)",
  },
  logo: { fontSize: 40, marginBottom: 8 },
  title: { fontSize: 28, fontWeight: 700, color: "#0f3460", margin: "0 0 4px" },
  sub: { color: "#666", marginBottom: 32, fontSize: 15 },
  googleBtn: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    width: "100%",
    padding: "12px 0",
    border: "1.5px solid #ddd",
    borderRadius: 8,
    background: "#fff",
    cursor: "pointer",
    fontSize: 15,
    fontWeight: 600,
    color: "#333",
    transition: "box-shadow .15s",
  },
  input: {
    width: "100%",
    padding: "10px 12px",
    border: "1.5px solid #ddd",
    borderRadius: 8,
    fontSize: 15,
    marginBottom: 12,
    boxSizing: "border-box",
  },
  btn: {
    width: "100%",
    padding: "11px 0",
    background: "#0f3460",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    fontSize: 15,
    fontWeight: 600,
    cursor: "pointer",
  },
  err: { color: "#c33", fontSize: 13, marginBottom: 10 },
  spinner: { fontSize: 32, marginBottom: 16 },
};

function SignInScreen({ onSignIn }) {
  return (
    <div style={s.screen}>
      <div style={s.card}>
        <div style={s.logo}>🎓</div>
        <h1 style={s.title}>AcadeMong</h1>
        <p style={s.sub}>ผู้ช่วย AI สำหรับการเลือกคณะและวางแผนอาชีพ</p>
        <button style={s.googleBtn} onClick={onSignIn}>
          <svg width="20" height="20" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          เข้าสู่ระบบด้วย Google
        </button>
      </div>
    </div>
  );
}

function RegisterScreen({ onRegister, error }) {
  const [username, setUsername] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    await onRegister(username.trim());
    setSubmitting(false);
  };

  return (
    <div style={s.screen}>
      <div style={s.card}>
        <div style={s.logo}>🎓</div>
        <h1 style={s.title}>ตั้งชื่อผู้ใช้</h1>
        <p style={s.sub}>เลือก username สำหรับบัญชีของคุณ (ตัวอักษร, ตัวเลข, _)</p>
        <form onSubmit={handleSubmit}>
          {error && <p style={s.err}>{error}</p>}
          <input
            style={s.input}
            placeholder="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            pattern="^[a-zA-Z0-9_]+$"
            minLength={3}
            maxLength={50}
            required
          />
          <button style={s.btn} type="submit" disabled={submitting}>
            {submitting ? "กำลังสร้างบัญชี..." : "เริ่มใช้งาน"}
          </button>
        </form>
      </div>
    </div>
  );
}

function LoadingScreen() {
  return (
    <div style={s.screen}>
      <div style={{ ...s.card, padding: 40 }}>
        <div style={s.spinner}>⏳</div>
        <p style={{ color: "#666" }}>กำลังโหลด...</p>
      </div>
    </div>
  );
}

export default function AuthGate({ children }) {
  const { authState, signIn, register, registerError, username, signOut, getToken } = useAuth();

  if (authState === "loading") return <LoadingScreen />;
  if (authState === "signed-out") return <SignInScreen onSignIn={signIn} />;
  if (authState === "needs-register") return <RegisterScreen onRegister={register} error={registerError} />;

  return children({ getToken, username, signOut });
}
