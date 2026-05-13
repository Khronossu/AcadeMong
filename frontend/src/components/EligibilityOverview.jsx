import { useEffect, useState } from "react";
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell, ReferenceLine,
} from "recharts";

const NEW_SYSTEM_YEAR = 2023;

const PALETTE = [
  "#0f3460", "#e94560", "#0a7", "#e6a817", "#7c3aed",
  "#0891b2", "#dc2626", "#059669", "#d97706", "#6366f1",
];

function linearRegression(points) {
  const n = points.length;
  if (n < 2) return null;
  const sumX = points.reduce((s, p) => s + p.x, 0);
  const sumY = points.reduce((s, p) => s + p.y, 0);
  const sumXY = points.reduce((s, p) => s + p.x * p.y, 0);
  const sumX2 = points.reduce((s, p) => s + p.x * p.x, 0);
  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#fff", border: "1px solid #ddd", borderRadius: 8, padding: "8px 12px", fontSize: 12, maxWidth: 260 }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>ปี {label}</div>
      {payload.map((p) => p.value != null && (
        <div key={p.name} style={{ color: p.color, marginBottom: 2 }}>
          <span style={{ fontSize: 11 }}>{p.name}:</span> {Number(p.value).toLocaleString()}
        </div>
      ))}
    </div>
  );
};

export default function EligibilityOverview({ results, getToken }) {
  const [open, setOpen] = useState(true);
  const [trendData, setTrendData] = useState(null);
  const [loadingTrend, setLoadingTrend] = useState(false);

  const eligible = results.filter((r) => r.eligible);
  const ineligible = results.filter((r) => !r.eligible);

  // Bar chart: eligible vs ineligible by university
  const univMap = {};
  for (const r of results) {
    if (!univMap[r.university]) univMap[r.university] = { university: r.university, ผ่านเกณฑ์: 0, ไม่ผ่าน: 0 };
    if (r.eligible) univMap[r.university].ผ่านเกณฑ์++;
    else univMap[r.university].ไม่ผ่าน++;
  }
  const univData = Object.values(univMap).sort((a, b) => b.ผ่านเกณฑ์ - a.ผ่านเกณฑ์);

  // Avg competition ratio from eligible programs that have data (if loaded)
  const avgRatio = trendData
    ? (() => {
        const ratios = Object.values(trendData)
          .map((cuts) => {
            const last = cuts[cuts.length - 1];
            return last?.applicants_count && last?.accepted_count
              ? last.applicants_count / last.accepted_count : null;
          })
          .filter(Boolean);
        return ratios.length ? (ratios.reduce((s, r) => s + r, 0) / ratios.length).toFixed(1) : null;
      })()
    : null;

  // Fetch batch cutoffs for top 8 eligible programs
  useEffect(() => {
    if (!open || trendData) return;
    const topEligible = eligible.slice(0, 8);
    if (!topEligible.length) return;

    const controller = new AbortController();
    setLoadingTrend(true);

    (async () => {
      try {
        const token = await getToken();
        if (controller.signal.aborted) return;
        const res = await fetch("/api/chat/cutoffs/batch", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ ids: topEligible.map((r) => r.admission_project_id) }),
          signal: controller.signal,
        });
        const data = await res.json();
        setTrendData(data.cutoffs || {});
      } catch (e) {
        if (e.name !== "AbortError") setTrendData({});
      } finally {
        if (!controller.signal.aborted) setLoadingTrend(false);
      }
    })();

    return () => controller.abort();
  }, [open]);

  // Build multi-line chart data
  const programLabels = {};
  for (const r of eligible.slice(0, 8)) {
    programLabels[r.admission_project_id] = `${r.major} (${r.university.replace("มหาวิทยาลัย", "ม.").replace("จุฬาลงกรณ์", "จุฬาฯ")})`;
  }

  let multiLineData = [];
  if (trendData) {
    const allYears = new Set();
    Object.values(trendData).forEach((cuts) =>
      cuts.filter((c) => c.year >= NEW_SYSTEM_YEAR).forEach((c) => allYears.add(c.year))
    );
    const years = [...allYears].sort();

    // Add one projected year for trendlines
    const nextYear = years.length ? Math.max(...years) + 1 : null;
    const allYearsWithNext = nextYear ? [...years, nextYear] : years;

    // Compute regression per program — new exam system only (2023+)
    const NEW_SYSTEM_YEAR = 2023;
    const regressions = {};
    Object.entries(trendData).forEach(([id, cuts]) => {
      const pts = cuts.filter((c) => c.year >= NEW_SYSTEM_YEAR && c.min_admitted_score != null)
        .map((c) => ({ x: c.year, y: c.min_admitted_score }));
      regressions[id] = linearRegression(pts);
    });

    multiLineData = allYearsWithNext.map((year) => {
      const row = { year };
      Object.entries(trendData).forEach(([id, cuts]) => {
        const match = cuts.find((c) => c.year === year && c.year >= NEW_SYSTEM_YEAR);
        row[id] = match?.min_admitted_score ?? null;
        // Trend projection for last year
        if (year === nextYear && regressions[id]) {
          const { slope, intercept } = regressions[id];
          row[`trend_${id}`] = Math.round((slope * year + intercept) * 10) / 10;
        }
      });
      return row;
    });
  }

  return (
    <div style={s.wrapper}>
      <div style={s.toggleBar} onClick={() => setOpen(!open)}>
        <span style={s.toggleLabel}>ภาพรวมสถิติ</span>
        <span style={s.toggleIcon}>{open ? "▲" : "▼"}</span>
      </div>

      {open && (
        <div style={s.body}>
          {/* Stat cards */}
          <div style={s.cards}>
            <StatCard label="ผ่านเกณฑ์" value={eligible.length} color="#0a7" />
            <StatCard label="ไม่ผ่านเกณฑ์" value={ineligible.length} color="#c33" />
            <StatCard label="อัตราผ่านเกณฑ์" value={`${Math.round(eligible.length / results.length * 100)}%`} color="#0f3460" />
            {avgRatio && <StatCard label="อัตราการแข่งขันเฉลี่ย" value={`${avgRatio}:1`} color="#e94560" />}
          </div>

          {/* Bar chart by university */}
          <div style={s.chartBlock}>
            <div style={s.chartTitle}>โครงการผ่าน/ไม่ผ่านเกณฑ์ แยกตามมหาวิทยาลัย</div>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={univData} margin={{ top: 4, right: 8, left: 0, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="university" tick={{ fontSize: 10 }} angle={-20} textAnchor="end" interval={0} />
                <YAxis tick={{ fontSize: 11 }} width={30} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="ผ่านเกณฑ์" fill="#0a7" radius={[4, 4, 0, 0]} />
                <Bar dataKey="ไม่ผ่าน" fill="#e0e0e0" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Multi-program trend comparison */}
          <div style={s.chartBlock}>
            <div style={s.chartTitle}>
              เปรียบเทียบแนวโน้มคะแนนขั้นต่ำ — โครงการที่ผ่านเกณฑ์ (สูงสุด 8 โครงการ)
            </div>
            {loadingTrend ? (
              <div style={s.loading}>กำลังโหลดข้อมูลแนวโน้ม...</div>
            ) : multiLineData.length === 0 ? (
              <div style={s.loading}>ไม่มีข้อมูลคะแนนย้อนหลัง</div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={multiLineData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="year" tick={{ fontSize: 12 }} />
                    <YAxis
                      tick={{ fontSize: 11 }} width={65}
                      tickFormatter={(v) => v?.toLocaleString()}
                      domain={[(dataMin) => Math.max(0, Math.floor(dataMin * 0.92 / 100) * 100), (dataMax) => Math.ceil(dataMax * 1.05 / 100) * 100]}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend
                      wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                      formatter={(value) => programLabels[value] || value}
                    />
                    {Object.keys(trendData || {}).map((id, i) => (
                      <Line
                        key={id}
                        type="monotone"
                        dataKey={id}
                        name={id}
                        stroke={PALETTE[i % PALETTE.length]}
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        connectNulls={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
                <div style={s.note}>แต่ละสีแทนหนึ่งโครงการ | เส้นประแดง = คาดการณ์ปีถัดไป</div>

                {/* Applicant count comparison */}
                {Object.keys(trendData || {}).length > 0 && (() => {
                  const appData = multiLineData.map((row) => {
                    const r = { year: row.year };
                    Object.entries(trendData).forEach(([id, cuts]) => {
                      const match = cuts.find((c) => c.year === row.year);
                      r[id] = match?.applicants_count ?? null;
                    });
                    return r;
                  }).filter((r) => Object.entries(r).some(([k, v]) => k !== "year" && v != null));
                  return appData.length ? (
                    <>
                      <div style={{ ...s.chartTitle, marginTop: 16 }}>เปรียบเทียบจำนวนผู้สมัครต่อปี</div>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={appData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
                          <YAxis tick={{ fontSize: 11 }} width={60} tickFormatter={(v) => v?.toLocaleString()}
                            domain={[0, (dataMax) => Math.ceil(dataMax * 1.1 / 10) * 10]} />
                          <Tooltip content={<CustomTooltip />} />
                          <Legend wrapperStyle={{ fontSize: 11 }} formatter={(value) => programLabels[value] || value} />
                          {Object.keys(trendData).map((id, i) => (
                            <Line key={id} type="monotone" dataKey={id} name={id}
                              stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </>
                  ) : null;
                })()}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={s.card}>
      <div style={{ ...s.cardValue, color }}>{value}</div>
      <div style={s.cardLabel}>{label}</div>
    </div>
  );
}

const s = {
  wrapper: { border: "1px solid #dde", borderRadius: 10, marginBottom: "1.25rem", overflow: "hidden" },
  toggleBar: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "0.6rem 1rem", background: "#f0f4ff", cursor: "pointer", userSelect: "none",
  },
  toggleLabel: { fontWeight: 700, fontSize: "0.9rem", color: "#1a1a2e" },
  toggleIcon: { color: "#888", fontSize: "0.85rem" },
  body: { padding: "1rem" },
  cards: { display: "flex", gap: 12, flexWrap: "wrap", marginBottom: "1rem" },
  card: {
    flex: "1 1 100px", background: "#f8f9ff", borderRadius: 10,
    padding: "0.75rem 1rem", textAlign: "center", border: "1px solid #e8eaf0",
  },
  cardValue: { fontSize: "1.5rem", fontWeight: 800, lineHeight: 1.2 },
  cardLabel: { fontSize: "0.78rem", color: "#666", marginTop: 4 },
  chartBlock: { marginBottom: "1rem" },
  chartTitle: { fontWeight: 600, fontSize: "0.85rem", color: "#333", marginBottom: 8 },
  loading: { color: "#aaa", fontSize: "0.85rem", textAlign: "center", padding: "1.5rem 0" },
  note: { fontSize: "0.75rem", color: "#aaa", textAlign: "center", marginTop: 4 },
};
