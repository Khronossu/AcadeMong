import { useState, useEffect } from "react";

export default function CareerPathView({ getToken }) {
  const [recs, setRecs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      try {
        const token = await getToken();
        if (controller.signal.aborted) return;
        const res = await fetch("/api/profile/career-recommendations", {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        setRecs(data.recommendations || []);
      } catch (e) {
        if (e.name !== "AbortError") setError("โหลดข้อมูลไม่สำเร็จ: " + e.message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, []);

  if (loading) return <p style={s.hint}>กำลังโหลด...</p>;
  if (error) return <p style={{ color: "#c33" }}>{error}</p>;

  return (
    <div style={s.container}>
      <h2 style={s.heading}>อาชีพแนะนำสำหรับคุณ</h2>
      {recs.length === 0 ? (
        <div style={s.empty}>
          <p style={s.emptyText}>ยังไม่มีอาชีพแนะนำ</p>
          <p style={s.hint}>ลองคุยกับ AI 1 (Career Dreamer) เพื่อให้ระบบวิเคราะห์จุดแข็งและความสนใจของคุณก่อนนะคะ</p>
        </div>
      ) : (
        <div style={s.grid}>
          {recs.map((rec, i) => (
            <CareerCard key={i} rec={rec} />
          ))}
        </div>
      )}
    </div>
  );
}

function CareerCard({ rec }) {
  const [open, setOpen] = useState(false);
  const score = rec.match_score ? Math.round(rec.match_score * 100) : null;

  return (
    <div style={s.card}>
      <div style={s.cardHeader} onClick={() => setOpen(!open)}>
        <div style={s.cardLeft}>
          <div style={s.titleRow}>
            <span style={s.title}>{rec.title}</span>
            {score !== null && (
              <span style={{ ...s.scoreBadge, background: score >= 80 ? "#0a7" : score >= 60 ? "#e6a817" : "#888" }}>
                {score}% เข้ากัน
              </span>
            )}
          </div>
          {rec.industry_group && <div style={s.industry}>{rec.industry_group}</div>}
          {rec.avg_salary_thb && (
            <div style={s.salary}>เงินเดือนเฉลี่ย {rec.avg_salary_thb.toLocaleString()} บาท/เดือน</div>
          )}
        </div>
        <span style={s.toggle}>{open ? "▲" : "▼"}</span>
      </div>

      {open && (
        <div style={s.cardBody}>
          {rec.overview_description && <p style={s.overview}>{rec.overview_description}</p>}
          {rec.ai_reasoning && (
            <div style={s.reasoningBox}>
              <div style={s.reasoningLabel}>เหตุผลที่แนะนำ</div>
              <p style={s.reasoning}>{rec.ai_reasoning}</p>
            </div>
          )}
          {rec.top_skills && Array.isArray(rec.top_skills) && rec.top_skills.length > 0 && (
            <div style={s.skills}>
              <div style={s.skillsLabel}>ทักษะที่ต้องการ</div>
              <div style={s.skillTags}>
                {rec.top_skills.map((sk, i) => <span key={i} style={s.tag}>{sk}</span>)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const s = {
  container: { maxWidth: 800, margin: "0 auto", padding: "1rem" },
  heading: { color: "#1a1a2e", marginBottom: "0.5rem" },
  hint: { color: "#666", marginBottom: "1rem", lineHeight: 1.6 },
  empty: { textAlign: "center", padding: "3rem 1rem" },
  emptyText: { fontSize: "1.1rem", color: "#555", marginBottom: "0.5rem" },
  grid: { display: "flex", flexDirection: "column", gap: "0.75rem" },
  card: { border: "1px solid #e0e0e0", borderRadius: 10, overflow: "hidden", background: "#fff" },
  cardHeader: {
    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
    padding: "1rem", cursor: "pointer", background: "#fafafa",
  },
  cardLeft: { flex: 1 },
  titleRow: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 },
  title: { fontSize: "1rem", fontWeight: 700, color: "#1a1a2e" },
  scoreBadge: { color: "#fff", borderRadius: 12, padding: "0.15rem 0.6rem", fontSize: "0.78rem", fontWeight: 600 },
  industry: { color: "#888", fontSize: "0.82rem", marginBottom: 2 },
  salary: { color: "#0a7", fontSize: "0.85rem", fontWeight: 600 },
  toggle: { color: "#888", paddingTop: 2, marginLeft: 8 },
  cardBody: { padding: "0.75rem 1rem", borderTop: "1px solid #eee" },
  overview: { color: "#444", fontSize: "0.9rem", lineHeight: 1.6, marginBottom: "0.75rem" },
  reasoningBox: { background: "#f0f4ff", borderRadius: 8, padding: "0.75rem", marginBottom: "0.75rem" },
  reasoningLabel: { fontWeight: 600, fontSize: "0.82rem", color: "#0f3460", marginBottom: 4 },
  reasoning: { color: "#333", fontSize: "0.88rem", lineHeight: 1.6, margin: 0 },
  skills: { marginTop: "0.5rem" },
  skillsLabel: { fontWeight: 600, fontSize: "0.82rem", color: "#555", marginBottom: 6 },
  skillTags: { display: "flex", flexWrap: "wrap", gap: 6 },
  tag: { background: "#eef2ff", color: "#0f3460", borderRadius: 20, padding: "0.2rem 0.65rem", fontSize: "0.8rem" },
};
