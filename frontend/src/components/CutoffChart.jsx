import { useEffect, useState } from "react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ReferenceLine,
} from "recharts";

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

function buildTrendData(data, key) {
  const valid = data.filter((d) => d[key] != null);
  if (valid.length < 2) return [];
  const reg = linearRegression(valid.map((d) => ({ x: d.year, y: d[key] })));
  if (!reg) return [];
  const allYears = [...valid.map((d) => d.year), valid[valid.length - 1].year + 1];
  return allYears.map((year) => ({
    year,
    trend: Math.round((reg.slope * year + reg.intercept) * 100) / 100,
  }));
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#fff", border: "1px solid #ddd", borderRadius: 8, padding: "8px 12px", fontSize: 13 }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>ปี {label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color }}>
          {p.name}: {p.value != null ? p.value.toLocaleString() : "–"}
        </div>
      ))}
    </div>
  );
};

export default function CutoffChart({ admissionProjectId, getToken }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const token = await getToken();
        const res = await fetch(`/api/chat/cutoffs/${admissionProjectId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) { setData([]); return; }
        const json = await res.json();
        setData(json.cutoffs || []);
      } catch {
        setData([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [admissionProjectId]);

  if (loading) return <div style={s.placeholder}>กำลังโหลดข้อมูลคะแนนย้อนหลัง...</div>;
  if (!data || data.length === 0) return <div style={s.placeholder}>ไม่มีข้อมูลคะแนนย้อนหลัง</div>;

  // Merge cutoff data + trend into one array keyed by year
  const trendData = buildTrendData(data, "min_admitted_score");
  const trendByYear = Object.fromEntries(trendData.map((d) => [d.year, d.trend]));

  const chartData = [
    ...data.map((d) => ({
      year: d.year,
      min: d.min_admitted_score,
      max: d.max_admitted_score,
      median: d.median_score,
      trend: trendByYear[d.year] ?? null,
    })),
    // Append next-year trend projection
    ...(trendData.length
      ? [{ year: trendData[trendData.length - 1].year, min: null, max: null, median: null, trend: trendData[trendData.length - 1].trend }]
      : []),
  ].sort((a, b) => a.year - b.year);

  const lastYear = data[data.length - 1];
  const trendDir = trendData.length >= 2
    ? trendData[trendData.length - 1].trend - trendData[trendData.length - 2].trend
    : 0;

  return (
    <div style={s.container}>
      <div style={s.header}>
        <span style={s.title}>คะแนนย้อนหลัง {data[0].year}–{lastYear.year}</span>
        {trendData.length >= 2 && (
          <span style={{ ...s.trendBadge, background: trendDir > 0 ? "#fee" : trendDir < 0 ? "#efe" : "#f5f5f5",
            color: trendDir > 0 ? "#c33" : trendDir < 0 ? "#0a7" : "#888" }}>
            {trendDir > 0 ? "↑ แนวโน้มสูงขึ้น" : trendDir < 0 ? "↓ แนวโน้มลดลง" : "→ ทรงตัว"}
          </span>
        )}
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 11 }} width={55} tickFormatter={(v) => v?.toLocaleString()} />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone" dataKey="min" name="คะแนนต่ำสุด"
            stroke="#0f3460" strokeWidth={2} dot={{ r: 4 }} connectNulls={false}
          />
          <Line
            type="monotone" dataKey="max" name="คะแนนสูงสุด"
            stroke="#aab" strokeWidth={1.5} dot={{ r: 3 }} strokeDasharray="4 2" connectNulls={false}
          />
          <Line
            type="monotone" dataKey="trend" name="แนวโน้ม"
            stroke="#e94560" strokeWidth={1.5} dot={false} strokeDasharray="6 3" connectNulls
          />
        </LineChart>
      </ResponsiveContainer>

      <div style={s.stats}>
        <div style={s.stat}>
          <span style={s.statLabel}>คะแนนต่ำสุดล่าสุด</span>
          <span style={s.statValue}>{lastYear.min_admitted_score?.toLocaleString() ?? "–"}</span>
        </div>
        <div style={s.stat}>
          <span style={s.statLabel}>ผู้สมัคร</span>
          <span style={s.statValue}>{lastYear.applicants_count?.toLocaleString() ?? "–"}</span>
        </div>
        <div style={s.stat}>
          <span style={s.statLabel}>รับจริง</span>
          <span style={s.statValue}>{lastYear.accepted_count?.toLocaleString() ?? "–"}</span>
        </div>
        {lastYear.applicants_count && lastYear.accepted_count && (
          <div style={s.stat}>
            <span style={s.statLabel}>อัตราการแข่งขัน</span>
            <span style={{ ...s.statValue, color: "#e94560" }}>
              {(lastYear.applicants_count / lastYear.accepted_count).toFixed(1)}:1
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

const s = {
  container: { marginTop: 12, background: "#f8f9ff", borderRadius: 8, padding: "10px 12px" },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 },
  title: { fontWeight: 600, fontSize: "0.85rem", color: "#1a1a2e" },
  trendBadge: { fontSize: "0.78rem", fontWeight: 600, padding: "2px 8px", borderRadius: 12 },
  placeholder: { color: "#aaa", fontSize: "0.85rem", padding: "12px 0", textAlign: "center" },
  stats: { display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8, paddingTop: 8, borderTop: "1px solid #eee" },
  stat: { display: "flex", flexDirection: "column", gap: 2 },
  statLabel: { fontSize: "0.75rem", color: "#888" },
  statValue: { fontSize: "0.9rem", fontWeight: 700, color: "#1a1a2e" },
};
