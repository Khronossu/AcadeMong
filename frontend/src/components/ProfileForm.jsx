import { useState, useEffect } from "react";

const SUBJECTS = [
  "TGAT1", "TGAT2", "TGAT3", "TGAT",
  "TPAT1", "TPAT2", "TPAT3", "TPAT4", "TPAT5",
  "A_LEVEL_MATH1", "A_LEVEL_MATH2",
  "A_LEVEL_PHYSICS", "A_LEVEL_CHEMISTRY", "A_LEVEL_BIOLOGY", "A_LEVEL_GENERAL_SCIENCE",
  "A_LEVEL_THAI", "A_LEVEL_ENGLISH", "A_LEVEL_SOCIAL_STUDIES",
];

const CURRENT_YEAR = new Date().getFullYear();

export default function ProfileForm({ token, onSaved }) {
  const [gpax, setGpax] = useState("");
  const [school, setSchool] = useState("");
  const [scores, setScores] = useState([{ subject: "TGAT1", score: "", exam_year: CURRENT_YEAR }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetch("/api/profile/me", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.gpax != null) setGpax(String(data.gpax));
        if (data.current_school) setSchool(data.current_school);
        if (data.test_scores?.length) {
          setScores(data.test_scores.map((s) => ({
            subject: s.subject,
            score: String(s.score),
            exam_year: s.exam_year,
          })));
        }
      })
      .catch(() => {});
  }, [token]);

  function addScore() {
    setScores((prev) => [...prev, { subject: "TGAT1", score: "", exam_year: CURRENT_YEAR }]);
  }

  function removeScore(i) {
    setScores((prev) => prev.filter((_, idx) => idx !== i));
  }

  function updateScore(i, field, value) {
    setScores((prev) => prev.map((s, idx) => idx === i ? { ...s, [field]: value } : s));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    setSaving(true);

    const validScores = scores
      .filter((s) => s.score !== "" && !isNaN(parseFloat(s.score)))
      .map((s) => ({
        subject: s.subject,
        score: parseFloat(s.score),
        exam_year: parseInt(s.exam_year, 10),
      }));

    const body = {
      gpax: gpax !== "" ? parseFloat(gpax) : null,
      current_school: school || null,
      test_scores: validScores,
    };

    try {
      const res = await fetch("/api/profile/me", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || "Save failed");
      }
      setSuccess(true);
      onSaved?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={styles.form}>
      <h2 style={styles.heading}>โปรไฟล์นักเรียน</h2>

      <label style={styles.label}>GPAX (0.00 – 4.00)</label>
      <input
        style={styles.input}
        type="number"
        step="0.01"
        min="0"
        max="4"
        value={gpax}
        onChange={(e) => setGpax(e.target.value)}
        placeholder="เช่น 3.75"
      />

      <label style={styles.label}>โรงเรียนปัจจุบัน</label>
      <input
        style={styles.input}
        type="text"
        value={school}
        onChange={(e) => setSchool(e.target.value)}
        placeholder="ชื่อโรงเรียน"
      />

      <h3 style={styles.subheading}>คะแนนสอบ</h3>
      {scores.map((s, i) => (
        <div key={i} style={styles.scoreRow}>
          <select
            style={styles.select}
            value={s.subject}
            onChange={(e) => updateScore(i, "subject", e.target.value)}
          >
            {SUBJECTS.map((subj) => (
              <option key={subj} value={subj}>{subj}</option>
            ))}
          </select>
          <input
            style={{ ...styles.input, width: "80px", margin: "0 8px" }}
            type="number"
            step="0.01"
            min="0"
            max="100"
            value={s.score}
            onChange={(e) => updateScore(i, "score", e.target.value)}
            placeholder="คะแนน"
          />
          <input
            style={{ ...styles.input, width: "70px", margin: "0 8px 0 0" }}
            type="number"
            min="2020"
            max="2100"
            value={s.exam_year}
            onChange={(e) => updateScore(i, "exam_year", e.target.value)}
          />
          <button type="button" onClick={() => removeScore(i)} style={styles.removeBtn}>✕</button>
        </div>
      ))}
      <button type="button" onClick={addScore} style={styles.addBtn}>+ เพิ่มวิชา</button>

      {error && <p style={styles.error}>{error}</p>}
      {success && <p style={styles.success}>บันทึกสำเร็จ</p>}

      <button type="submit" disabled={saving || !token} style={styles.saveBtn}>
        {saving ? "กำลังบันทึก..." : "บันทึกโปรไฟล์"}
      </button>
    </form>
  );
}

const styles = {
  form: { maxWidth: 600, margin: "0 auto", padding: "1rem" },
  heading: { color: "#1a1a2e", marginBottom: "1rem" },
  subheading: { color: "#16213e", margin: "1.2rem 0 0.5rem" },
  label: { display: "block", marginBottom: "0.25rem", fontWeight: 600, fontSize: "0.9rem" },
  input: {
    display: "block", width: "100%", padding: "0.45rem 0.6rem",
    marginBottom: "0.8rem", border: "1px solid #ccc", borderRadius: 6,
    fontSize: "0.95rem", boxSizing: "border-box",
  },
  select: {
    padding: "0.45rem 0.6rem", border: "1px solid #ccc",
    borderRadius: 6, fontSize: "0.95rem",
  },
  scoreRow: { display: "flex", alignItems: "center", marginBottom: "0.5rem", flexWrap: "wrap" },
  addBtn: {
    background: "none", border: "1px dashed #888", borderRadius: 6,
    padding: "0.35rem 0.75rem", cursor: "pointer", marginBottom: "1rem",
    color: "#555", fontSize: "0.9rem",
  },
  removeBtn: {
    background: "none", border: "none", cursor: "pointer",
    color: "#c00", fontSize: "1rem", padding: "0 4px",
  },
  saveBtn: {
    background: "#0f3460", color: "#fff", border: "none", borderRadius: 8,
    padding: "0.6rem 1.5rem", cursor: "pointer", fontSize: "1rem",
    marginTop: "0.5rem", opacity: 1,
  },
  error: { color: "#c00", marginBottom: "0.5rem" },
  success: { color: "#080", marginBottom: "0.5rem" },
};
