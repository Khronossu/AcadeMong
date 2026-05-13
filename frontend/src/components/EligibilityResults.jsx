import { useState } from "react";
import CutoffChart from "./CutoffChart";
import EligibilityOverview from "./EligibilityOverview";
import { t } from "../theme";

const GROUP_OPTIONS = [
  { key: "university", label: "มหาวิทยาลัย" },
  { key: "faculty",    label: "คณะ" },
  { key: "field",      label: "สาขาวิชา" },
  { key: "none",       label: "ทั้งหมด" },
];

function groupBy(items, key) {
  const map = {};
  for (const item of items) {
    const k = (key === "none" ? "ทั้งหมด" : item[key]) || "ไม่ระบุ";
    if (!map[k]) map[k] = [];
    map[k].push(item);
  }
  return Object.entries(map).sort(([a], [b]) => a.localeCompare(b, "th"));
}

function groupByMajor(items) {
  // Group projects under their parent major (major_id)
  const map = {};
  for (const item of items) {
    const key = item.major_id || item.major;
    if (!map[key]) map[key] = { major: item.major, faculty: item.faculty, university: item.university, major_id: item.major_id, projects: [] };
    map[key].projects.push(item);
  }
  // Sort: majors with eligible projects first, then alphabetically
  return Object.values(map).sort((a, b) => {
    const aElig = a.projects.some((p) => p.eligible) ? 0 : 1;
    const bElig = b.projects.some((p) => p.eligible) ? 0 : 1;
    if (aElig !== bElig) return aElig - bElig;
    return a.major.localeCompare(b.major, "th");
  });
}

export default function EligibilityResults({ getToken }) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("eligible");
  const [groupKey, setGroupKey] = useState("university");

  async function runCheck() {
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const token = await getToken();
      const res = await fetch("/api/chat/eligibility", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || "ไม่สามารถตรวจสอบสิทธิ์ได้");
      }
      setResults(await res.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const filtered = results?.results?.filter((r) => {
    if (filter === "eligible") return r.eligible;
    if (filter === "ineligible") return !r.eligible;
    return true;
  }) ?? [];

  const groups = groupBy(filtered, groupKey);
  const eligibleTotal = results?.eligible_count ?? 0;
  const total = results?.total_projects ?? 0;

  return (
    <div style={cs.container}>
      <h2 style={cs.heading}>ตรวจสอบคุณสมบัติ TCAS รอบ 3</h2>
      <p style={cs.hint}>
        กดปุ่มด้านล่างเพื่อดูโครงการรับสมัครทั้งหมดที่คุณมีสิทธิ์สมัคร<br />
        (บันทึก GPAX และคะแนนสอบในแท็บ "โปรไฟล์" ก่อน)
      </p>

      <button onClick={runCheck} disabled={loading} style={cs.checkBtn}>
        {loading ? "กำลังตรวจสอบ..." : "ตรวจสอบคุณสมบัติ"}
      </button>

      {error && <p style={cs.error}>{error}</p>}

      {results && (
        <>
          <div style={cs.summary}>
            <span style={cs.badge}>ปีการศึกษา {results.year}</span>
            <span style={{ ...cs.badge, background: "#0a7" }}>
              ผ่านเกณฑ์ {eligibleTotal} / {total} โครงการ
            </span>
          </div>

          <div style={cs.controls}>
            <div style={cs.controlGroup}>
              <span style={cs.controlLabel}>แสดง:</span>
              {[["all", "ทั้งหมด"], ["eligible", "ผ่านเกณฑ์"], ["ineligible", "ไม่ผ่าน"]].map(([v, l]) => (
                <button key={v} onClick={() => setFilter(v)}
                  style={{ ...cs.pill, ...(filter === v ? cs.pillActive : {}) }}>{l}</button>
              ))}
            </div>
            <div style={cs.controlGroup}>
              <span style={cs.controlLabel}>จัดกลุ่มตาม:</span>
              {GROUP_OPTIONS.map(({ key, label }) => (
                <button key={key} onClick={() => setGroupKey(key)}
                  style={{ ...cs.pill, ...(groupKey === key ? cs.pillActive : {}) }}>{label}</button>
              ))}
            </div>
          </div>

          <EligibilityOverview results={results.results} getToken={getToken} />

          {filtered.length === 0 ? (
            <p style={cs.empty}>ไม่มีโครงการในหมวดนี้</p>
          ) : (
            groups.map(([groupName, items]) => (
              <GroupSection
                key={groupName}
                name={groupName}
                items={items}
                getToken={getToken}
                defaultOpen={groups.length <= 3}
              />
            ))
          )}
        </>
      )}
    </div>
  );
}

function GroupSection({ name, items, getToken, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);
  const eligibleCount = items.filter((r) => r.eligible).length;
  const majorGroups = groupByMajor(items);

  return (
    <div style={gs.section}>
      <div style={gs.header} onClick={() => setOpen(!open)}>
        <div style={gs.headerLeft}>
          <span style={gs.groupName}>{name}</span>
          <span style={{ ...gs.count, color: eligibleCount > 0 ? "#0a7" : "#c33" }}>
            ผ่านเกณฑ์ {eligibleCount}/{items.length} โครงการ · {majorGroups.length} หลักสูตร
          </span>
        </div>
        <span style={gs.toggle}>{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div style={gs.body}>
          {majorGroups.map((mg) => (
            <MajorCard key={mg.major_id || mg.major} majorGroup={mg} getToken={getToken} />
          ))}
        </div>
      )}
    </div>
  );
}

function MajorCard({ majorGroup, getToken }) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const { major, faculty, major_id, projects } = majorGroup;
  const eligibleCount = projects.filter((p) => p.eligible).length;
  const allEligible = eligibleCount === projects.length;
  const anyEligible = eligibleCount > 0;
  const headerColor = allEligible ? "#0a7" : anyEligible ? "#e6a817" : "#c33";

  async function handleSave(e) {
    e.stopPropagation();
    if (!major_id || saving || saved) return;
    setSaving(true);
    try {
      const token = await getToken();
      const res = await fetch("/api/profile/saved-majors", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ major_id }),
      });
      if (res.ok) setSaved(true);
    } finally { setSaving(false); }
  }

  return (
    <div style={{ ...mc.card, borderLeft: `4px solid ${headerColor}` }}>
      {/* Major header — click to expand */}
      <div style={mc.header} onClick={() => setOpen(!open)}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={mc.majorName}>{major}</div>
          <div style={mc.meta}>
            {faculty}
            <span style={mc.dot}>·</span>
            <span style={{ ...mc.eligCount, color: headerColor }}>
              {eligibleCount}/{projects.length} โครงการผ่านเกณฑ์
            </span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {major_id && getToken && (
            <button onClick={handleSave} disabled={saving || saved} style={{
              padding: "3px 10px", border: "1.5px solid", borderRadius: 20, fontSize: "0.75rem",
              cursor: saved ? "default" : "pointer", fontWeight: 600, whiteSpace: "nowrap",
              borderColor: saved ? "#0a7" : "#0f3460",
              color: saved ? "#0a7" : "#0f3460", background: "#fff",
            }}>
              {saved ? "✓ บันทึก" : saving ? "..." : "บันทึก"}
            </button>
          )}
          <span style={mc.toggle}>{open ? "▲" : "▼"}</span>
        </div>
      </div>

      {/* Project rows — shown when expanded */}
      {open && (
        <div style={mc.projectList}>
          {projects.map((p) => (
            <ProjectRow key={p.admission_project_id} result={p} getToken={getToken} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectRow({ result, getToken }) {
  const [open, setOpen] = useState(false);
  const borderColor = result.eligible ? "#0a7" : "#c33";

  return (
    <div style={pr.row}>
      {/* Project summary line — click to expand details */}
      <div style={pr.summary} onClick={() => setOpen(!open)}>
        <span style={{ ...pr.badge, background: borderColor }}>
          {result.eligible ? "ผ่าน" : "ไม่ผ่าน"}
        </span>
        <span style={pr.projectName}>{result.project_name}</span>
        <div style={pr.rightMeta}>
          {result.gpax_min != null && (
            <span style={pr.gpaxTag}>GPAX ≥ {result.gpax_min.toFixed(2)}</span>
          )}
          {result.seats && <span style={pr.seatsTag}>{result.seats} ที่นั่ง</span>}
          <span style={pr.toggle}>{open ? "▲" : "▼"}</span>
        </div>
      </div>

      {/* Expanded details */}
      {open && (
        <div style={pr.details}>
          {result.subject_results.length > 0 && (
            <>
              <div style={styles.subHeading}>วิชาที่ใช้</div>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>วิชา</th>
                    <th style={styles.th}>ขั้นต่ำ</th>
                    <th style={styles.th}>คะแนนคุณ</th>
                    <th style={styles.th}>น้ำหนัก</th>
                    <th style={styles.th}>สถานะ</th>
                  </tr>
                </thead>
                <tbody>
                  {result.subject_results.map((s) => (
                    <tr key={s.subject}>
                      <td style={styles.td}>{s.subject}</td>
                      <td style={styles.td}>{s.min_score ?? "–"}</td>
                      <td style={styles.td}>{s.student_score ?? "ไม่มีข้อมูล"}</td>
                      <td style={styles.td}>{s.weight_percent != null ? `${s.weight_percent}%` : "–"}</td>
                      <td style={styles.td}>
                        <span style={s.ok ? styles.pass : styles.fail}>{s.ok ? "✓" : "✗"}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <CutoffChart admissionProjectId={result.admission_project_id} getToken={getToken} />

          {result.source_url && (
            <a href={result.source_url} target="_blank" rel="noreferrer" style={styles.link}>
              ดูประกาศรับสมัคร →
            </a>
          )}
        </div>
      )}
    </div>
  );
}

// Legacy export for any other file that imports ProjectCard directly
export function ProjectCard({ result, getToken }) {
  return <ProjectRow result={result} getToken={getToken} />;
}

const cs = {
  container: { maxWidth: 860, margin: "0 auto", padding: "1.5rem 2rem", fontFamily: "'Inter','Sarabun',sans-serif" },
  heading: { color: t.text1, fontSize: 18, fontWeight: 700 },
  hint: { color: t.text3, marginBottom: "1rem", lineHeight: 1.6, fontSize: 13 },
  checkBtn: {
    background: t.accent, color: "#fff", border: "none", borderRadius: 8,
    padding: "0.6rem 1.5rem", cursor: "pointer", fontSize: "0.95rem", marginBottom: "1rem", fontFamily: "inherit",
  },
  error: { color: t.fail, fontSize: 13 },
  summary: { display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" },
  badge: { background: t.accent, color: "#fff", borderRadius: 20, padding: "0.25rem 0.75rem", fontSize: "0.82rem" },
  controls: { display: "flex", flexDirection: "column", gap: 8, marginBottom: "1.25rem" },
  controlGroup: { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" },
  controlLabel: { fontSize: "0.82rem", color: t.text3, minWidth: 90 },
  pill: { border: `1px solid ${t.border}`, borderRadius: 20, padding: "0.2rem 0.7rem", cursor: "pointer", background: t.surface, fontSize: "0.82rem", color: t.text2, fontFamily: "inherit" },
  pillActive: { background: t.accent, color: "#fff", border: `1px solid ${t.accent}` },
  empty: { color: t.text3, textAlign: "center", padding: "2rem" },
};

const gs = {
  section: { marginBottom: "0.75rem", border: `1px solid ${t.border}`, borderRadius: 10, overflow: "hidden" },
  header: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "0.75rem 1rem", cursor: "pointer", background: t.card, userSelect: "none",
  },
  headerLeft: { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" },
  groupName: { fontWeight: 700, color: t.text1, fontSize: "0.95rem" },
  count: { fontSize: "0.82rem", fontWeight: 600 },
  toggle: { color: t.text3, fontSize: "0.9rem" },
  body: { padding: "0.5rem 0.75rem", background: t.bg },
};

const mc = {
  card: {
    border: "1px solid #e8e8e8", borderRadius: 8, marginBottom: "0.5rem",
    overflow: "hidden", background: "#fff",
  },
  header: {
    display: "flex", alignItems: "center", gap: 10,
    padding: "0.75rem 1rem", cursor: "pointer", background: "#fafafa",
  },
  majorName: { fontWeight: 700, color: "#1a1a2e", fontSize: "0.95rem", marginBottom: 2 },
  meta: { display: "flex", alignItems: "center", gap: 6, fontSize: "0.82rem", color: "#666", flexWrap: "wrap" },
  dot: { color: "#ccc" },
  eligCount: { fontWeight: 600 },
  toggle: { color: "#888", fontSize: "0.85rem" },
  projectList: { borderTop: "1px solid #f0f0f0" },
};

const pr = {
  row: { borderBottom: "1px solid #f5f5f5" },
  summary: {
    display: "flex", alignItems: "center", gap: 8, padding: "0.55rem 1rem",
    cursor: "pointer", background: "#fff", flexWrap: "wrap",
  },
  badge: {
    color: "#fff", borderRadius: 10, padding: "0.1rem 0.45rem",
    fontSize: "0.7rem", fontWeight: 600, whiteSpace: "nowrap", flexShrink: 0,
  },
  projectName: { flex: 1, fontSize: "0.88rem", color: "#333", minWidth: 0 },
  rightMeta: { display: "flex", alignItems: "center", gap: 6, flexShrink: 0 },
  gpaxTag: { fontSize: "0.75rem", color: "#888", background: "#f5f5f5", padding: "1px 6px", borderRadius: 8 },
  seatsTag: { fontSize: "0.75rem", color: "#888" },
  toggle: { color: "#aaa", fontSize: "0.8rem" },
  details: { padding: "0.75rem 1rem", background: "#fafafa", borderTop: "1px solid #eee" },
};

const styles = {
  subHeading: { fontWeight: 600, margin: "0.5rem 0 0.35rem", fontSize: "0.88rem", color: "#333" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" },
  th: { textAlign: "left", padding: "0.3rem 0.5rem", borderBottom: "1px solid #ddd", color: "#555" },
  td: { padding: "0.3rem 0.5rem", borderBottom: "1px solid #f0f0f0" },
  pass: { color: "#0a7", fontWeight: 600 },
  fail: { color: "#c33", fontWeight: 600 },
  link: { color: "#0f3460", fontSize: "0.82rem", display: "inline-block", marginTop: "0.5rem" },
};
