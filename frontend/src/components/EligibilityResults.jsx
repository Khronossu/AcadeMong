import { useState } from "react";
import CutoffChart from "./CutoffChart";
import { t } from "../theme";
import Icon from "./Icon";

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
      const res = await fetch((import.meta.env.VITE_API_BASE||"")+"/api/chat/eligibility", {
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

  // Show large hero when idle (no results yet, not loading)
  if (!results && !loading && !error) {
    return (
      <div style={eh.page}>
        <div style={eh.card}>
          <div style={eh.iconWrap}>
            <Icon name="check-circle" size={52} color={t.accent} />
          </div>
          <h1 style={eh.title}>ตรวจสอบสิทธิ์ TCAS</h1>
          <p style={eh.sub}>
            ระบบเปรียบเทียบ GPAX และคะแนนสอบของคุณกับทุกโครงการรับสมัคร
            <br />แบบเรียลไทม์ ไม่ต้องค้นหาเอง
          </p>
          <div style={eh.stats}>
            {[["5", "มหาวิทยาลัย"], ["100+", "โครงการ"], ["TCAS 3", "รอบ Admission"]].map(([num, lbl], i, arr) => (
              <div key={lbl} style={{ ...eh.stat, ...(i === arr.length - 1 ? { borderRight: "none" } : {}) }}>
                <span style={eh.statNum}>{num}</span>
                <span style={eh.statLabel}>{lbl}</span>
              </div>
            ))}
          </div>
          <button style={eh.cta} onClick={runCheck}>
            ตรวจสอบเลย
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ marginLeft: 8 }}>
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
          <p style={eh.prereq}>บันทึก GPAX และคะแนนสอบในแท็บ "โปรไฟล์" ก่อนนะ</p>
        </div>
      </div>
    );
  }

  return (
    <div style={cs.outer}>
      {/* Sticky controls — stay visible while results scroll */}
      <div style={cs.stickyTop}>
        <div style={cs.topRow}>
          <h2 style={cs.heading}>ตรวจสอบคุณสมบัติ TCAS รอบ 3</h2>
          <button onClick={runCheck} disabled={loading} style={cs.checkBtn}>
            {loading ? "กำลังตรวจสอบ..." : "ตรวจสอบใหม่"}
          </button>
        </div>

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
          </>
        )}
      </div>

      {/* Scrollable results body — expands/collapses without touching the controls */}
      {results && (
        <div style={cs.scrollBody}>
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
        </div>
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
      const res = await fetch((import.meta.env.VITE_API_BASE||"")+"/api/profile/saved-majors", {
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

const eh = {
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
  sub: { fontSize: 16, color: t.text2, lineHeight: 1.7, margin: "0 0 28px" },
  stats: { display: "flex", justifyContent: "center", gap: 0, marginBottom: 32, border: `1px solid ${t.border}`, borderRadius: 12, overflow: "hidden" },
  stat: { flex: 1, padding: "14px 8px", display: "flex", flexDirection: "column", alignItems: "center", gap: 4, borderRight: `1px solid ${t.border}` },
  statNum: { fontSize: 22, fontWeight: 800, color: t.accent },
  statLabel: { fontSize: 12, color: t.text3 },
  cta: {
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    background: t.accent, color: "#fff", border: "none",
    borderRadius: 12, padding: "14px 28px",
    fontSize: 16, fontWeight: 700, cursor: "pointer",
    fontFamily: "inherit", width: "100%", marginBottom: 16,
    transition: "background .15s",
  },
  prereq: { fontSize: 13, color: t.text3, margin: 0 },
};

const cs = {
  outer: { maxWidth: 860, margin: "0 auto", width: "100%", fontFamily: "'Inter','Sarabun',sans-serif", fontSize: 14 },
  stickyTop: {
    position: "sticky", top: 0, zIndex: 10,
    background: t.bg, padding: "24px 32px 16px",
    borderBottom: `1px solid ${t.border}`,
  },
  scrollBody: { padding: "16px 32px 40px" },
  topRow: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 12, flexWrap: "wrap" },
  heading: { color: t.text1, fontSize: 18, fontWeight: 700, margin: 0 },
  checkBtn: {
    background: t.accent, color: "#fff", border: "none", borderRadius: 8,
    padding: "8px 20px", cursor: "pointer", fontSize: 14, fontFamily: "inherit",
  },
  hint: { color: t.text3, marginBottom: 16, lineHeight: 1.6, fontSize: 13 },
  error: { color: t.fail, fontSize: 13 },
  summary: { display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" },
  badge: { background: t.accent, color: "#fff", borderRadius: 20, padding: "3px 12px", fontSize: 13 },
  controls: { display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 },
  controlGroup: { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" },
  controlLabel: { fontSize: 13, color: t.text3, minWidth: 90 },
  pill: { border: `1px solid ${t.border}`, borderRadius: 20, padding: "3px 11px", cursor: "pointer", background: t.surface, fontSize: 13, color: t.text2, fontFamily: "inherit" },
  pillActive: { background: t.accent, color: "#fff", border: `1px solid ${t.accent}` },
  empty: { color: t.text3, textAlign: "center", padding: 32 },
};

const gs = {
  section: { marginBottom: 10, border: `1px solid ${t.border}`, borderRadius: 10, overflow: "hidden" },
  header: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "12px 16px", cursor: "pointer", background: t.card, userSelect: "none",
  },
  headerLeft: { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" },
  groupName: { fontWeight: 700, color: t.text1, fontSize: 14 },
  count: { fontSize: 13, fontWeight: 600 },
  toggle: { color: t.text3, fontSize: 13 },
  body: { padding: "8px 12px", background: t.bg },
};

const mc = {
  card: {
    border: `1px solid ${t.border}`, borderRadius: 8, marginBottom: 8,
    overflow: "hidden", background: t.surface,
  },
  header: {
    display: "flex", alignItems: "center", gap: 10,
    padding: "12px 16px", cursor: "pointer", background: t.card,
  },
  majorName: { fontWeight: 700, color: t.text1, fontSize: 14, marginBottom: 2 },
  meta: { display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: t.text2, flexWrap: "wrap" },
  dot: { color: t.borderMd },
  eligCount: { fontWeight: 600 },
  toggle: { color: t.text3, fontSize: 13 },
  projectList: { borderTop: `1px solid ${t.border}` },
};

const pr = {
  row: { borderBottom: `1px solid ${t.border}` },
  summary: {
    display: "flex", alignItems: "center", gap: 8, padding: "9px 16px",
    cursor: "pointer", background: t.surface, flexWrap: "wrap",
  },
  badge: {
    color: "#fff", borderRadius: 10, padding: "2px 7px",
    fontSize: 12, fontWeight: 600, whiteSpace: "nowrap", flexShrink: 0,
  },
  projectName: { flex: 1, fontSize: 13, color: t.text1, minWidth: 0 },
  rightMeta: { display: "flex", alignItems: "center", gap: 6, flexShrink: 0 },
  gpaxTag: { fontSize: 12, color: t.text3, background: t.card, padding: "1px 6px", borderRadius: 8 },
  seatsTag: { fontSize: 12, color: t.text3 },
  toggle: { color: t.text3, fontSize: 13 },
  details: { padding: "12px 16px", background: t.card, borderTop: `1px solid ${t.border}` },
};

const styles = {
  subHeading: { fontWeight: 600, margin: "8px 0 6px", fontSize: 13, color: t.text2 },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 13 },
  th: { textAlign: "left", padding: "5px 8px", borderBottom: `1px solid ${t.border}`, color: t.text2 },
  td: { padding: "5px 8px", borderBottom: `1px solid ${t.border}` },
  pass: { color: t.pass, fontWeight: 600 },
  fail: { color: t.fail, fontWeight: 600 },
  link: { color: t.accent, fontSize: 13, display: "inline-block", marginTop: 8 },
};
