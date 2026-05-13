import { useState, useEffect } from "react";
import { t } from "../theme";

const SUBJECTS = [
  "TGAT1", "TGAT2", "TGAT3", "TGAT",
  "TPAT1", "TPAT2", "TPAT3", "TPAT4", "TPAT5",
  "A_LEVEL_MATH1", "A_LEVEL_MATH2",
  "A_LEVEL_PHYSICS", "A_LEVEL_CHEMISTRY", "A_LEVEL_BIOLOGY", "A_LEVEL_GENERAL_SCIENCE",
  "A_LEVEL_THAI", "A_LEVEL_ENGLISH", "A_LEVEL_SOCIAL_STUDIES",
];

const INTEREST_TAGS = [
  "วิทยาศาสตร์", "คณิตศาสตร์", "เทคโนโลยี", "วิศวกรรม",
  "แพทยศาสตร์", "เภสัชศาสตร์", "ทันตแพทยศาสตร์", "พยาบาลศาสตร์",
  "ศิลปะ", "ดนตรี", "สถาปัตยกรรม", "การออกแบบ",
  "บริหารธุรกิจ", "การตลาด", "การเงิน", "การบัญชี",
  "นิติศาสตร์", "รัฐศาสตร์", "สังคมศาสตร์", "มนุษยศาสตร์",
  "ภาษาต่างประเทศ", "สื่อสารมวลชน", "นิเทศศาสตร์",
  "เกษตรศาสตร์", "สิ่งแวดล้อม", "การกีฬา",
];

const TARGET_UNIVERSITIES = [
  "จุฬาลงกรณ์มหาวิทยาลัย",
  "มหาวิทยาลัยมหิดล",
  "มหาวิทยาลัยเกษตรศาสตร์",
  "มหาวิทยาลัยธรรมศาสตร์",
  "มหาวิทยาลัยศรีนครินทรวิโรฒ",
];

const CURRENT_YEAR = new Date().getFullYear();

export default function ProfileForm({ getToken, onSaved }) {
  const [gpax, setGpax] = useState("");
  const [school, setSchool] = useState("");
  const [interests, setInterests] = useState([]);
  const [targetUniversities, setTargetUniversities] = useState([]);
  const [scores, setScores] = useState([{ subject: "TGAT1", score: "", exam_year: CURRENT_YEAR }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    getToken()
      .then((token) => fetch("/api/profile/me", { headers: { Authorization: `Bearer ${token}` } }))
      .then((r) => r.json())
      .then((data) => {
        if (data.gpax != null) setGpax(String(data.gpax));
        if (data.current_school) setSchool(data.current_school);
        if (data.interests?.length) setInterests(data.interests);
        if (data.target_universities?.length) setTargetUniversities(data.target_universities);
        if (data.test_scores?.length) {
          setScores(data.test_scores.map((s) => ({
            subject: s.subject,
            score: String(s.score),
            exam_year: s.exam_year,
          })));
        }
      })
      .catch(() => {});
  }, []);

  function toggleInterest(tag) {
    setInterests((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  }

  function toggleUniversity(name) {
    setTargetUniversities((prev) =>
      prev.includes(name) ? prev.filter((u) => u !== name) : [...prev, name]
    );
  }

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
      interests: interests.length ? interests : null,
      target_universities: targetUniversities.length ? targetUniversities : null,
      test_scores: validScores,
    };

    try {
      const token = await getToken();
      const res = await fetch("/api/profile/me", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
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
        type="number" step="0.01" min="0" max="4"
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

      {/* Interests */}
      <h3 style={styles.subheading}>ความสนใจ</h3>
      <p style={styles.hint}>เลือกสาขาที่สนใจ (เลือกได้หลายอย่าง)</p>
      <div style={styles.tagGrid}>
        {INTEREST_TAGS.map((tag) => (
          <button
            key={tag}
            type="button"
            onClick={() => toggleInterest(tag)}
            style={{
              ...styles.tag,
              ...(interests.includes(tag) ? styles.tagActive : {}),
            }}
          >
            {tag}
          </button>
        ))}
      </div>

      {/* Target universities */}
      <h3 style={styles.subheading}>มหาวิทยาลัยที่สนใจ</h3>
      <div style={styles.univList}>
        {TARGET_UNIVERSITIES.map((u) => (
          <label key={u} style={styles.univRow}>
            <input
              type="checkbox"
              checked={targetUniversities.includes(u)}
              onChange={() => toggleUniversity(u)}
              style={{ marginRight: 8 }}
            />
            {u}
          </label>
        ))}
      </div>

      {/* Test scores */}
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
            type="number" step="0.01" min="0" max="100"
            value={s.score}
            onChange={(e) => updateScore(i, "score", e.target.value)}
            placeholder="คะแนน"
          />
          <input
            style={{ ...styles.input, width: "70px", margin: "0 8px 0 0" }}
            type="number" min="2020" max="2100"
            value={s.exam_year}
            onChange={(e) => updateScore(i, "exam_year", e.target.value)}
          />
          <button type="button" onClick={() => removeScore(i)} style={styles.removeBtn}>✕</button>
        </div>
      ))}
      <button type="button" onClick={addScore} style={styles.addBtn}>+ เพิ่มวิชา</button>

      {error && <p style={styles.error}>{error}</p>}
      {success && <p style={styles.success}>บันทึกสำเร็จ ✓</p>}

      <button type="submit" disabled={saving} style={styles.saveBtn}>
        {saving ? "กำลังบันทึก..." : "บันทึกโปรไฟล์"}
      </button>
    </form>
  );
}

const styles = {
  form: { maxWidth: 640, margin: "0 auto", padding: "1.5rem 2rem", fontFamily: "'Inter','Sarabun',sans-serif" },
  heading: { color: t.text1, marginBottom: "1rem", fontSize: 18, fontWeight: 700 },
  subheading: { color: t.text1, margin: "1.2rem 0 0.4rem", fontSize: 15, fontWeight: 600 },
  hint: { color: t.text3, fontSize: "0.85rem", margin: "0 0 0.6rem" },
  label: { display: "block", marginBottom: "0.25rem", fontWeight: 600, fontSize: "0.9rem", color: t.text2 },
  input: {
    display: "block", width: "100%", padding: "0.5rem 0.7rem",
    marginBottom: "0.8rem", border: `1.5px solid ${t.border}`, borderRadius: 8,
    fontSize: "0.95rem", boxSizing: "border-box", background: t.card,
    color: t.text1, fontFamily: "inherit", outline: "none",
  },
  select: { padding: "0.5rem 0.7rem", border: `1.5px solid ${t.border}`, borderRadius: 8, fontSize: "0.9rem", background: t.card, color: t.text1, fontFamily: "inherit" },
  tagGrid: { display: "flex", flexWrap: "wrap", gap: 8, marginBottom: "0.75rem" },
  tag: {
    padding: "0.3rem 0.8rem", border: `1.5px solid ${t.border}`, borderRadius: 20,
    background: t.surface, cursor: "pointer", fontSize: "0.82rem", color: t.text2,
    transition: "all .15s", fontFamily: "inherit",
  },
  tagActive: { background: t.accent, color: "#fff", borderColor: t.accent },
  univList: { display: "flex", flexDirection: "column", gap: 10, marginBottom: "0.75rem" },
  univRow: { display: "flex", alignItems: "center", fontSize: "0.92rem", cursor: "pointer", color: t.text2 },
  scoreRow: { display: "flex", alignItems: "center", marginBottom: "0.5rem", flexWrap: "wrap" },
  addBtn: {
    background: "none", border: `1px dashed ${t.borderMd}`, borderRadius: 8,
    padding: "0.35rem 0.75rem", cursor: "pointer", marginBottom: "1rem",
    color: "#555", fontSize: "0.9rem",
  },
  removeBtn: { background: "none", border: "none", cursor: "pointer", color: t.fail, fontSize: "1rem", padding: "0 4px" },
  saveBtn: {
    background: t.accent, color: "#fff", border: "none", borderRadius: 8,
    padding: "0.6rem 1.5rem", cursor: "pointer", fontSize: "1rem", marginTop: "0.5rem", fontFamily: "inherit",
  },
  error:   { color: t.fail, marginBottom: "0.5rem", fontSize: 13 },
  success: { color: t.pass, marginBottom: "0.5rem", fontSize: 13 },
};
