import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { crashed: false };
  }

  static getDerivedStateFromError() {
    return { crashed: true };
  }

  componentDidCatch(err, info) {
    console.error("ErrorBoundary caught:", err, info);
  }

  render() {
    if (this.state.crashed) {
      return (
        <div style={s.box}>
          <div style={s.icon}>⚠️</div>
          <div style={s.msg}>{this.props.fallback || "เกิดข้อผิดพลาด กรุณาลองใหม่"}</div>
          <button style={s.btn} onClick={() => this.setState({ crashed: false })}>
            ลองอีกครั้ง
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const s = {
  box: { padding: "2rem", textAlign: "center", color: "#555" },
  icon: { fontSize: 32, marginBottom: 8 },
  msg: { marginBottom: 12, fontSize: "0.95rem" },
  btn: {
    padding: "6px 18px", background: "#0f3460", color: "#fff",
    border: "none", borderRadius: 8, cursor: "pointer", fontSize: "0.9rem",
  },
};
