import { useState, useEffect } from "react";
import ConfirmDialog from "./ConfirmDialog";
import Icon from "./Icon";

export default function SavedMajorsView({ getToken }) {
  const [majors, setMajors] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null); // majorId to delete

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const token = await getToken();
        if (controller.signal.aborted) return;
        const res = await fetch("/api/profile/saved-majors", {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        setMajors(data.saved_majors || []);
      } catch (e) {
        if (e.name !== "AbortError") setError("โหลดข้อมูลไม่สำเร็จ: " + e.message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, []);

  async function handleDelete(majorId) {
    try {
      const token = await getToken();
      const res = await fetch(`/api/profile/saved-majors/${majorId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setMajors((prev) => prev.filter((m) => m.major_id !== majorId));
    } catch { /* graceful */ }
  }

  async function handleSaveNote(majorId, note) {
    try {
      const token = await getToken();
      await fetch("/api/profile/saved-majors", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ major_id: majorId, notes: note }),
      });
      setMajors((prev) => prev.map((m) => m.major_id === majorId ? { ...m, notes: note } : m));
    } catch { /* graceful */ }
  }

  if (loading) return <p style={s.hint}>กำลังโหลด...</p>;
  if (error) return <p style={{ color: "#c33" }}>{error}</p>;

  // Group by university
  const grouped = {};
  for (const m of majors) {
    const key = m.university_name || "ไม่ระบุมหาวิทยาลัย";
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(m);
  }
  const universities = Object.keys(grouped).sort();

  return (
    <div style={s.container}>
      {confirmDelete && (
        <ConfirmDialog
          message="ลบสาขานี้ออกจากรายการบันทึก?"
          confirmLabel="ลบ"
          onConfirm={() => { handleDelete(confirmDelete); setConfirmDelete(null); }}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      <div style={s.headerRow}>
        <h2 style={s.heading}>สาขาที่บันทึกไว้</h2>
        <span style={s.count}>{majors.length} สาขา</span>
      </div>
      <p style={s.hint}>บันทึกสาขาที่สนใจจากแท็บ "ตรวจสอบคุณสมบัติ" เพื่อเปรียบเทียบและวางแผน</p>

      {majors.length === 0 ? (
        <div style={s.empty}>
          <div style={s.emptyIcon}><Icon name="bookmark" size={40} color="#aaa" /></div>
          <p style={s.emptyText}>ยังไม่มีสาขาที่บันทึกไว้</p>
          <p style={s.hint}>ไปที่แท็บ "ตรวจสอบคุณสมบัติ" กดปุ่ม <strong>บันทึก</strong> บนโครงการที่สนใจ</p>
        </div>
      ) : (
        universities.map((univ) => (
          <UniversityGroup
            key={univ}
            university={univ}
            majors={grouped[univ]}
            onDelete={(id) => setConfirmDelete(id)}
            onSaveNote={handleSaveNote}
          />
        ))
      )}
    </div>
  );
}

function UniversityGroup({ university, majors, onDelete, onSaveNote }) {
  const [open, setOpen] = useState(true);
  return (
    <div style={s.group}>
      <div style={s.groupHeader} onClick={() => setOpen(!open)}>
        <span style={s.groupName}>{university}</span>
        <span style={s.groupCount}>{majors.length} สาขา</span>
        <span style={s.toggle}>{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div style={s.groupBody}>
          {majors.map((m) => (
            <MajorCard
              key={m.major_id}
              major={m}
              onDelete={onDelete}
              onSaveNote={onSaveNote}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function MajorCard({ major, onDelete, onSaveNote }) {
  const [editingNote, setEditingNote] = useState(false);
  const [noteValue, setNoteValue] = useState(major.notes || "");

  function handleNoteBlur() {
    setEditingNote(false);
    if (noteValue !== (major.notes || "")) {
      onSaveNote(major.major_id, noteValue);
    }
  }

  const savedDate = major.saved_at
    ? new Date(major.saved_at).toLocaleDateString("th-TH", { day: "numeric", month: "short", year: "numeric" })
    : null;

  return (
    <div style={s.card}>
      <div style={s.cardTop}>
        <div style={s.cardInfo}>
          <div style={s.majorName}>{major.major_name}</div>
          <div style={s.facultyName}>{major.faculty_name}</div>
          {savedDate && <div style={s.savedDate}>บันทึกเมื่อ {savedDate}</div>}
        </div>
        <button
          style={s.deleteBtn}
          onClick={() => onDelete(major.major_id)}
          title="ลบออกจากรายการ"
        >×</button>
      </div>

      {/* Notes section */}
      <div style={s.notesSection}>
        {editingNote ? (
          <textarea
            style={s.noteInput}
            value={noteValue}
            onChange={(e) => setNoteValue(e.target.value)}
            onBlur={handleNoteBlur}
            onKeyDown={(e) => { if (e.key === "Escape") { setEditingNote(false); setNoteValue(major.notes || ""); } }}
            placeholder="เพิ่มโน้ตส่วนตัว..."
            autoFocus
            rows={2}
          />
        ) : (
          <div style={s.noteDisplay} onClick={() => setEditingNote(true)}>
            {major.notes
              ? <span style={s.noteText}>{major.notes}</span>
              : <span style={s.notePlaceholder}>+ เพิ่มโน้ต...</span>
            }
          </div>
        )}
      </div>
    </div>
  );
}

const s = {
  container: { maxWidth: 800, margin: "0 auto", padding: "1rem" },
  headerRow: { display: "flex", alignItems: "center", gap: 12, marginBottom: 4 },
  heading: { color: "#1a1a2e", margin: 0 },
  count: { background: "#0f3460", color: "#fff", borderRadius: 20, padding: "2px 10px", fontSize: "0.82rem", fontWeight: 600 },
  hint: { color: "#666", fontSize: "0.88rem", marginBottom: "1rem", lineHeight: 1.6 },
  empty: { textAlign: "center", padding: "3rem 1rem" },
  emptyIcon: { fontSize: 40, marginBottom: 8 },
  emptyText: { fontSize: "1.1rem", color: "#555", marginBottom: "0.5rem" },
  group: { border: "1px solid #dde", borderRadius: 10, marginBottom: "0.75rem", overflow: "hidden" },
  groupHeader: {
    display: "flex", alignItems: "center", gap: 10,
    padding: "0.65rem 1rem", background: "#f0f4ff",
    cursor: "pointer", userSelect: "none",
  },
  groupName: { fontWeight: 700, color: "#1a1a2e", fontSize: "0.95rem", flex: 1 },
  groupCount: { fontSize: "0.78rem", color: "#0f3460", fontWeight: 600 },
  toggle: { color: "#888", fontSize: "0.85rem" },
  groupBody: { padding: "0.5rem 0.75rem" },
  card: {
    border: "1px solid #e8e8e8", borderRadius: 8, marginBottom: "0.5rem",
    background: "#fff", padding: "0.75rem 1rem",
  },
  cardTop: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 },
  cardInfo: { flex: 1 },
  majorName: { fontWeight: 700, color: "#1a1a2e", fontSize: "0.95rem", marginBottom: 2 },
  facultyName: { color: "#555", fontSize: "0.82rem", marginBottom: 2 },
  savedDate: { color: "#aaa", fontSize: "0.75rem" },
  deleteBtn: {
    background: "none", border: "none", color: "#ccc", cursor: "pointer",
    fontSize: "1.2rem", padding: "0 4px", lineHeight: 1, flexShrink: 0,
    transition: "color .15s",
  },
  notesSection: { marginTop: 8 },
  noteDisplay: {
    cursor: "text", padding: "4px 6px", borderRadius: 6,
    border: "1px dashed transparent", transition: "border .15s",
    minHeight: 24,
  },
  noteText: { fontSize: "0.85rem", color: "#444" },
  notePlaceholder: { fontSize: "0.82rem", color: "#bbb" },
  noteInput: {
    width: "100%", padding: "6px 8px", border: "1.5px solid #0f3460",
    borderRadius: 6, fontSize: "0.85rem", fontFamily: "Sarabun, sans-serif",
    resize: "none", boxSizing: "border-box", outline: "none",
  },
};
