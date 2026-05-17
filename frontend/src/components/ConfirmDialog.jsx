import { useEffect } from "react";
import { t } from "../theme";
import Icon from "./Icon";

export default function ConfirmDialog({ message, confirmLabel = "ลบ", onConfirm, onCancel }) {
  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel]);

  return (
    <div style={s.overlay} onClick={onCancel}>
      <div style={s.dialog} onClick={(e) => e.stopPropagation()}>
        <div style={s.icon}><Icon name="trash" size={32} color={t.fail} /></div>
        <div style={s.message}>{message}</div>
        <div style={s.actions}>
          <button style={s.cancelBtn} onClick={onCancel}>ยกเลิก</button>
          <button style={s.confirmBtn} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

const s = {
  overlay: {
    position: "fixed", inset: 0, zIndex: 999,
    background: "rgba(0,0,0,.55)", backdropFilter: "blur(2px)",
    display: "flex", alignItems: "center", justifyContent: "center",
    padding: 20,
  },
  dialog: {
    background: t.surface, border: `1px solid ${t.border}`,
    borderRadius: 16, padding: "28px 28px 22px",
    width: "100%", maxWidth: 360,
    boxShadow: "0 24px 60px rgba(0,0,0,.5)",
    display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
    fontFamily: "'Inter','Sarabun',sans-serif",
    animation: "dlg-in .15s ease",
  },
  icon:    { fontSize: 32, lineHeight: 1 },
  message: { fontSize: 17, color: t.text1, fontWeight: 600, textAlign: "center", lineHeight: 1.5 },
  actions: { display: "flex", gap: 10, marginTop: 8, width: "100%" },
  cancelBtn: {
    flex: 1, padding: "10px 0", border: `1px solid ${t.border}`,
    borderRadius: 10, background: t.card, color: t.text2,
    fontSize: 15, fontWeight: 500, cursor: "pointer", fontFamily: "inherit",
    transition: "background .12s",
  },
  confirmBtn: {
    flex: 1, padding: "10px 0", border: "none",
    borderRadius: 10, background: "#a05050", color: "#fff",
    fontSize: 15, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
    transition: "background .12s",
  },
};
