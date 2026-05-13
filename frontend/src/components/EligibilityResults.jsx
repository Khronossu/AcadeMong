import { useState } from "react";

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

          {/* Filter + Group controls */}
          <div style={cs.controls}>
            <div style={cs.controlGroup}>
              <span style={cs.controlLabel}>แสดง:</span>
              {[["all", "ทั้งหมด"], ["eligible", "ผ่านเกณฑ์"], ["ineligible", "ไม่ผ่าน"]].map(([v, l]) => (
                <button key={v} onClick={() => setFilter(v)}
                  style={{ ...cs.pill, ...(filter === v ? cs.pillActive : {}) }}>
                  {l}
                </button>
              ))}
            </div>
            <div style={cs.controlGroup}>
              <span style={cs.controlLabel}>จัดกลุ่มตาม:</span>
              {GROUP_OPTIONS.map(({ key, label }) => (
                <button key={key} onClick={() => setGroupKey(key)}
                  style={{ ...cs.pill, ...(groupKey === key ? cs.pillActive : {}) }}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Grouped results */}
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

  return (
    <div style={gs.section}>
      <div style={gs.header} onClick={() => setOpen(!open)}>
        <div style={gs.headerLeft}>
          <span style={gs.groupName}>{name}</span>
          <span style={{ ...gs.count, color: eligibleCount > 0 ? "#0a7" : "#c33" }}>
            ผ่านเกณฑ์ {eligibleCount}/{items.length}
          </span>
        </div>
        <span style={gs.toggle}>{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div style={gs.body}>
          {items.map((r) => (
            <ProjectCard key={r.admission_project_id} result={r} getToken={getToken} />
          ))}
        </div>
      )}
    </div>
  );
}

export function ProjectCard({ result, getToken }) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const borderColor = result.eligible ? "#0a7" : "#c33";

  async function handleSave(e) {
    e.stopPropagation();
    if (!result.major_id || saving || saved) return;
    setSaving(true);
    try {
      const token = await getToken();
      const res = await fetch("/api/profile/saved-majors", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ major_id: result.major_id }),
      });
      if (res.ok) setSaved(true);
    } finally { setSaving(false); }
  }

  return (
    <div style={{ ...styles.card, borderLeft: `4px solid ${borderColor}` }}>
      <div style={styles.cardHeader} onClick={() => setOpen(!open)}>
        <div style={{ flex: 1 }}>
          <div style={styles.topRow}>
            <span style={{ ...styles.eligibleBadge, background: borderColor }}>
              {result.eligible ? "ผ่านเกณฑ์" : "ไม่ผ่านเกณฑ์"}
            </span>
            <strong style={styles.projectName}>{result.project_name}</strong>
          </div>
          <div style={styles.location}>
            {result.university} › {result.faculty} › {result.major}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {result.major_id && getToken && (
            <button
              onClick={handleSave}
              disabled={saving || saved}
              style={{
                padding: "4px 10px", border: "1.5px solid", borderRadius: 20, fontSize: "0.78rem",
                cursor: saved ? "default" : "pointer", fontWeight: 600, whiteSpace: "nowrap",
                borderColor: saved ? "#0a7" : "#0f3460",
                color: saved ? "#0a7" : "#0f3460", background: "#fff",
              }}
            >
              {saved ? "✓ บันทึก" : saving ? "..." : "บันทึก"}
            </button>
          )}
          <span style={styles.toggle}>{open ? "▲" : "▼"}</span>
        </div>
      </div>

      {open && (
        <div style={styles.cardBody}>
          <div style={styles.row}>
            <span style={styles.key}>GPAX ขั้นต่ำ</span>
            <span style={result.gpax_ok ? styles.pass : styles.fail}>
              {result.gpax_min != null ? result.gpax_min.toFixed(2) : "ไม่กำหนด"}
              {!result.gpax_ok && " (ไม่ผ่าน)"}
            </span>
          </div>
          {result.seats && (
            <div style={styles.row}>
              <span style={styles.key}>จำนวนรับ</span>
              <span>{result.seats} คน</span>
            </div>
          )}

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

const cs = {
  container: { maxWidth: 860, margin: "0 auto", padding: "1rem" },
  heading: { color: "#1a1a2e" },
  hint: { color: "#555", marginBottom: "1rem", lineHeight: 1.6 },
  checkBtn: {
    background: "#0f3460", color: "#fff", border: "none", borderRadius: 8,
    padding: "0.6rem 1.5rem", cursor: "pointer", fontSize: "1rem", marginBottom: "1rem",
  },
  error: { color: "#c00" },
  summary: { display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" },
  badge: { background: "#0f3460", color: "#fff", borderRadius: 20, padding: "0.25rem 0.75rem", fontSize: "0.85rem" },
  controls: { display: "flex", flexDirection: "column", gap: 8, marginBottom: "1.25rem" },
  controlGroup: { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" },
  controlLabel: { fontSize: "0.82rem", color: "#666", minWidth: 90 },
  pill: {
    border: "1px solid #ccc", borderRadius: 20, padding: "0.2rem 0.7rem",
    cursor: "pointer", background: "#fff", fontSize: "0.82rem", color: "#555",
  },
  pillActive: { background: "#0f3460", color: "#fff", border: "1px solid #0f3460" },
  empty: { color: "#888", textAlign: "center", padding: "2rem" },
};

const gs = {
  section: { marginBottom: "0.75rem", border: "1px solid #dde", borderRadius: 10, overflow: "hidden" },
  header: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "0.75rem 1rem", cursor: "pointer",
    background: "#f0f4ff", userSelect: "none",
  },
  headerLeft: { display: "flex", alignItems: "center", gap: 10 },
  groupName: { fontWeight: 700, color: "#1a1a2e", fontSize: "0.95rem" },
  count: { fontSize: "0.82rem", fontWeight: 600 },
  toggle: { color: "#888", fontSize: "0.9rem" },
  body: { padding: "0.5rem 0.75rem" },
};

const styles = {
  card: { border: "1px solid #e8e8e8", borderRadius: 8, marginBottom: "0.5rem", overflow: "hidden", background: "#fff" },
  cardHeader: {
    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
    padding: "0.65rem 0.9rem", cursor: "pointer", background: "#fafafa", gap: 8,
  },
  topRow: { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: 2 },
  cardBody: { padding: "0.75rem 0.9rem", borderTop: "1px solid #eee" },
  projectName: { fontSize: "0.95rem" },
  location: { color: "#666", fontSize: "0.82rem" },
  eligibleBadge: { color: "#fff", borderRadius: 12, padding: "0.1rem 0.5rem", fontSize: "0.72rem", whiteSpace: "nowrap" },
  toggle: { color: "#888" },
  row: { display: "flex", gap: "1rem", marginBottom: "0.4rem", fontSize: "0.9rem" },
  key: { color: "#555", minWidth: 120 },
  subHeading: { fontWeight: 600, margin: "0.75rem 0 0.35rem", fontSize: "0.9rem" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" },
  th: { textAlign: "left", padding: "0.3rem 0.5rem", borderBottom: "1px solid #ddd", color: "#555" },
  td: { padding: "0.3rem 0.5rem", borderBottom: "1px solid #f0f0f0" },
  pass: { color: "#0a7", fontWeight: 600 },
  fail: { color: "#c33", fontWeight: 600 },
  link: { color: "#0f3460", fontSize: "0.85rem", display: "inline-block", marginTop: "0.5rem" },
};
