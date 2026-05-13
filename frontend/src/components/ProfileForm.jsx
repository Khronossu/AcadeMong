import { useState, useEffect, useRef } from "react";
import { t } from "../theme";
import Icon from "./Icon";

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

function SearchChips({ label, placeholder, allOptions, selected, onToggle }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef(null);

  const suggestions = allOptions.filter(
    (o) => !selected.includes(o) && (query === "" || o.toLowerCase().includes(query.toLowerCase()))
  );

  return (
    <div style={sc.wrap}>
      <label style={styles.label}>{label}</label>

      {/* Selected chips */}
      {selected.length > 0 && (
        <div style={sc.chips}>
          {selected.map((item) => (
            <span key={item} style={sc.chip}>
              {item}
              <button type="button" style={sc.chipX} onClick={() => onToggle(item)}>×</button>
            </span>
          ))}
        </div>
      )}

      {/* Search input */}
      <div style={sc.inputWrap}>
        <input
          ref={inputRef}
          style={sc.input}
          value={query}
          placeholder={placeholder}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        />
        {query && (
          <button type="button" style={sc.clearBtn} onMouseDown={() => setQuery("")}>×</button>
        )}
      </div>

      {/* Dropdown */}
      {open && suggestions.length > 0 && (
        <div style={sc.dropdown}>
          {suggestions.map((item) => (
            <div
              key={item}
              style={sc.dropItem}
              onMouseDown={(e) => { e.preventDefault(); onToggle(item); setQuery(""); inputRef.current?.focus(); }}
            >
              {item}
            </div>
          ))}
        </div>
      )}
      {open && suggestions.length === 0 && query.length > 0 && (
        <div style={sc.dropdown}>
          <div style={sc.dropEmpty}>ไม่พบรายการ</div>
        </div>
      )}
    </div>
  );
}

export default function ProfileForm({ getToken, onSaved }) {
  const [gpax, setGpax] = useState("");
  const [school, setSchool] = useState("");
  const [interests, setInterests] = useState([]);
  const [targetUniversities, setTargetUniversities] = useState([]);
  const [scores, setScores] = useState([{ subject: "TGAT1", score: "", exam_year: CURRENT_YEAR }]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    getToken()
      .then((token) => fetch("/api/profile/me", { headers: { Authorization: `Bearer ${token}` } }))
      .then((r) => r.json())
      .then((data) => {
        const hasData = data.gpax != null || data.test_scores?.length || data.interests?.length;
        if (hasData) setStarted(true);
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
    setInterests((prev) => prev.includes(tag) ? prev.filter((x) => x !== tag) : [...prev, tag]);
  }

  function toggleUniversity(name) {
    setTargetUniversities((prev) => prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name]);
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
      .map((s) => ({ subject: s.subject, score: parseFloat(s.score), exam_year: parseInt(s.exam_year, 10) }));

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

  if (!started) {
    return (
      <div style={hero.page}>
        <div style={hero.card}>
          <div style={hero.iconWrap}>
            <Icon name="person" size={48} color={t.accent} />
          </div>
          <h1 style={hero.title}>บอก AI เพื่อให้ช่วยได้ดีขึ้น</h1>
          <p style={hero.sub}>
            กรอกเกรดเฉลี่ย คะแนนสอบ และมหาวิทยาลัยที่สนใจ
            <br />เพื่อรับคำแนะนำที่แม่นยำและตรวจสอบสิทธิ์ได้ทันที
          </p>
          <div style={hero.features}>
            {[
              "ตรวจสอบสิทธิ์ TCAS อัตโนมัติ",
              "แนะนำคณะที่เหมาะกับโปรไฟล์คุณ",
              "ปรึกษา AI ได้อย่างแม่นยำยิ่งขึ้น",
            ].map((f) => (
              <div key={f} style={hero.feature}>
                <Icon name="check-circle" size={17} color={t.accent} />
                <span style={hero.featureText}>{f}</span>
              </div>
            ))}
          </div>
          <button style={hero.cta} onClick={() => setStarted(true)}>
            เริ่มกรอกข้อมูล
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ marginLeft: 8 }}>
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
    );
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

      {/* University search */}
      <SearchChips
        label="มหาวิทยาลัยที่สนใจ"
        placeholder="ค้นหามหาวิทยาลัย..."
        allOptions={TARGET_UNIVERSITIES}
        selected={targetUniversities}
        onToggle={toggleUniversity}
      />

      {/* Interest search */}
      <SearchChips
        label="ความสนใจ"
        placeholder="ค้นหาสาขาที่สนใจ..."
        allOptions={INTEREST_TAGS}
        selected={interests}
        onToggle={toggleInterest}
      />

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
            style={{ ...styles.input, width: "96px", margin: "0 8px 0 0" }}
            type="number" min="2020" max="2100"
            value={s.exam_year}
            onChange={(e) => updateScore(i, "exam_year", e.target.value)}
          />
          <button type="button" onClick={() => removeScore(i)} style={styles.removeBtn}>✕</button>
        </div>
      ))}
      <button type="button" onClick={addScore} style={styles.addBtn}>+ เพิ่มวิชา</button>

      <div style={styles.saveSection}>
        {error && <p style={styles.error}>{error}</p>}
        {success && <p style={styles.success}>บันทึกสำเร็จ ✓</p>}
        <button type="submit" disabled={saving} style={styles.saveBtn}>
          {saving ? "กำลังบันทึก..." : "บันทึกโปรไฟล์"}
        </button>
      </div>
    </form>
  );
}

const hero = {
  page: {
    minHeight: "100%", display: "flex", alignItems: "center", justifyContent: "center",
    padding: "2rem 1.5rem", background: t.bg, fontFamily: "'Inter','Sarabun',sans-serif",
  },
  card: {
    maxWidth: 480, width: "100%", textAlign: "center",
    background: t.surface, border: `1px solid ${t.border}`,
    borderRadius: 20, padding: "3rem 2.5rem",
    boxShadow: "0 8px 40px rgba(0,0,0,.06)",
  },
  iconWrap: { marginBottom: 20 },
  title: { fontSize: 28, fontWeight: 800, color: t.text1, margin: "0 0 12px", lineHeight: 1.25 },
  sub: {
    fontSize: 16, color: t.text2, lineHeight: 1.7,
    margin: "0 0 28px",
  },
  features: { display: "flex", flexDirection: "column", gap: 10, marginBottom: 32, textAlign: "left" },
  feature: { display: "flex", alignItems: "center", gap: 10 },
  featureText: { fontSize: 15, color: t.text2 },
  cta: {
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    background: t.accent, color: "#fff", border: "none",
    borderRadius: 12, padding: "14px 28px",
    fontSize: 16, fontWeight: 700, cursor: "pointer",
    fontFamily: "inherit", width: "100%",
    transition: "background .15s",
  },
};

const sc = {
  wrap: { position: "relative", marginBottom: "1.2rem" },
  chips: { display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 },
  chip: {
    display: "inline-flex", alignItems: "center", gap: 4,
    background: t.accentBg, border: `1px solid ${t.accent}`,
    borderRadius: 20, padding: "4px 10px",
    fontSize: 13, color: t.accent, fontWeight: 500,
  },
  chipX: {
    background: "none", border: "none", cursor: "pointer",
    color: t.accent, fontSize: 15, padding: "0 0 0 2px",
    lineHeight: 1, display: "flex", alignItems: "center",
  },
  inputWrap: { position: "relative" },
  input: {
    display: "block", width: "100%", padding: "10px 36px 10px 12px",
    border: `1.5px solid ${t.border}`, borderRadius: 8,
    fontSize: 14, boxSizing: "border-box", background: t.card,
    color: t.text1, fontFamily: "inherit", outline: "none",
  },
  clearBtn: {
    position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
    background: "none", border: "none", cursor: "pointer",
    color: t.text3, fontSize: 16, padding: 0, lineHeight: 1,
  },
  dropdown: {
    position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
    background: t.surface, border: `1.5px solid ${t.border}`,
    borderRadius: 8, zIndex: 20,
    boxShadow: "0 8px 24px rgba(0,0,0,.1)",
    maxHeight: 220, overflowY: "auto",
  },
  dropItem: {
    padding: "10px 14px", cursor: "pointer", fontSize: 14, color: t.text1,
    borderBottom: `1px solid ${t.border}`,
    transition: "background .1s",
  },
  dropEmpty: { padding: "10px 14px", fontSize: 13, color: t.text3 },
};

const styles = {
  form: { maxWidth: 640, margin: "0 auto", padding: "1.5rem 2rem", fontFamily: "'Inter','Sarabun',sans-serif" },
  heading: { color: t.text1, marginBottom: "1.2rem", fontSize: 20, fontWeight: 700 },
  subheading: { color: t.text1, margin: "1.2rem 0 0.4rem", fontSize: 15, fontWeight: 600 },
  label: { display: "block", marginBottom: "0.3rem", fontWeight: 600, fontSize: 14, color: t.text2 },
  input: {
    display: "block", width: "100%", padding: "10px 12px",
    marginBottom: "1rem", border: `1.5px solid ${t.border}`, borderRadius: 8,
    fontSize: 14, boxSizing: "border-box", background: t.card,
    color: t.text1, fontFamily: "inherit", outline: "none",
  },
  select: { padding: "10px 12px", border: `1.5px solid ${t.border}`, borderRadius: 8, fontSize: 14, background: t.card, color: t.text1, fontFamily: "inherit" },
  scoreRow: { display: "flex", alignItems: "center", marginBottom: "0.5rem", flexWrap: "wrap" },
  addBtn: {
    background: "none", border: `1px dashed ${t.borderMd}`, borderRadius: 8,
    padding: "0.35rem 0.75rem", cursor: "pointer", marginBottom: "0.5rem",
    color: t.text3, fontSize: 14,
  },
  removeBtn: { background: "none", border: "none", cursor: "pointer", color: t.fail, fontSize: "1rem", padding: "0 4px" },
  saveSection: {
    marginTop: 40, paddingTop: 20, borderTop: `1px solid ${t.border}`,
  },
  saveBtn: {
    background: t.accent, color: "#fff", border: "none", borderRadius: 8,
    padding: "10px 24px", cursor: "pointer", fontSize: 15, fontFamily: "inherit", fontWeight: 600,
  },
  error:   { color: t.fail, marginBottom: "0.5rem", fontSize: 13 },
  success: { color: t.pass, marginBottom: "0.5rem", fontSize: 13 },
};
