import { useState } from "react";

export function ProjectCard({ result }) {
  const [open, setOpen] = useState(false);
  const borderColor = result.eligible ? "#0a7" : "#c33";

  return (
    <div style={{ ...styles.card, borderLeft: `4px solid ${borderColor}` }}>
      <div style={styles.cardHeader} onClick={() => setOpen(!open)}>
        <div>
          <span style={{ ...styles.eligibleBadge, background: borderColor }}>
            {result.eligible ? "ผ่านเกณฑ์" : "ไม่ผ่านเกณฑ์"}
          </span>
          <strong style={styles.projectName}>{result.project_name}</strong>
          <div style={styles.location}>
            {result.university} › {result.faculty} › {result.major}
          </div>
        </div>
        <span style={styles.toggle}>{open ? "▲" : "▼"}</span>
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
                        <span style={s.ok ? styles.pass : styles.fail}>
                          {s.ok ? "✓" : "✗"}
                        </span>
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

const styles = {
  card: {
    border: "1px solid #e0e0e0", borderRadius: 8, marginBottom: "0.75rem",
    overflow: "hidden",
  },
  cardHeader: {
    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
    padding: "0.75rem 1rem", cursor: "pointer", background: "#fafafa",
  },
  cardBody: { padding: "0.75rem 1rem", borderTop: "1px solid #eee" },
  projectName: { display: "block", fontSize: "1rem", margin: "0.25rem 0" },
  location: { color: "#666", fontSize: "0.85rem" },
  eligibleBadge: {
    color: "#fff", borderRadius: 12, padding: "0.1rem 0.5rem",
    fontSize: "0.75rem", marginRight: "0.5rem",
  },
  toggle: { color: "#888", paddingTop: "0.25rem" },
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
