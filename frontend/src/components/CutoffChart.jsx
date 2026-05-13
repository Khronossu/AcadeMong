import { useEffect, useState } from "react";
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
} from "recharts";

function linearRegression(points) {
  const n = points.length;
  if (n < 2) return null;
  const sumX = points.reduce((s, p) => s + p.x, 0);
  const sumY = points.reduce((s, p) => s + p.y, 0);
  const sumXY = points.reduce((s, p) => s + p.x * p.y, 0);
  const sumX2 = points.reduce((s, p) => s + p.x * p.x, 0);
  const denom = n * sumX2 - sumX * sumX;
  if (denom === 0) return null;
  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

function project(reg, year) {
  if (!reg) return null;
  return Math.max(0, Math.round((reg.slope * year + reg.intercept) * 10) / 10);
}

const CustomTooltip = ({ active, payload, label, suffix }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#fff", border: "1px solid #ddd", borderRadius: 8, padding: "8px 12px", fontSize: 13 }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>
        {String(label).length === 4 && Number(label) > 2019 ? `ปี ${label}` : label}
      </div>
      {payload.map((p) => p.value != null && (
        <div key={p.name} style={{ color: p.color, marginBottom: 2 }}>
          {p.name}: <strong>{Number(p.value).toLocaleString()}</strong>{suffix ? ` ${suffix}` : ""}
        </div>
      ))}
    </div>
  );
};

const NEW_SYSTEM_YEAR = 2023; // TGAT/TPAT/A-Level replaced PAT/O-NET

function ScoreChart({ data }) {
  // Only use new-system years for trendline (2023+)
  const newSystemData = data.filter((d) => d.year >= NEW_SYSTEM_YEAR && d.min != null);
  const reg = linearRegression(newSystemData.map((d) => ({ x: d.year, y: d.min })));
  const lastYear = data[data.length - 1]?.year;
  const nextYear = lastYear + 1;

  // Y axis bounds from new-system data only (old system had different score ranges)
  const relevantValues = (newSystemData.length ? newSystemData : data)
    .flatMap((d) => [d.min, d.max].filter(Boolean));
  const minVal = relevantValues.length ? Math.min(...relevantValues) : 0;
  const maxVal = relevantValues.length ? Math.max(...relevantValues) : 100;
  const padding = (maxVal - minVal) * 0.15 || 1000;
  const yMin = Math.max(0, Math.floor((minVal - padding) / 100) * 100);
  const yMax = Math.ceil((maxVal + padding) / 100) * 100;

  // Append projected year
  const chartData = [
    ...data,
    { year: nextYear, min: null, max: null, trend: project(reg, nextYear), isForecast: true },
  ];

  const trendDir = reg ? reg.slope : 0;

  return (
    <div>
      <div style={s.chartHeader}>
        <span style={s.chartLabel}>คะแนนขั้นต่ำ–สูงสุด (คะแนนรวมถ่วงน้ำหนัก)</span>
        {reg && (
          <span style={{ ...s.badge, background: trendDir > 0 ? "#fee" : trendDir < 0 ? "#efe" : "#f5f5f5",
            color: trendDir > 0 ? "#c33" : trendDir < 0 ? "#0a7" : "#888" }}>
            {trendDir > 50 ? "↑ สูงขึ้นเร็ว" : trendDir > 0 ? "↑ สูงขึ้น" : trendDir < -50 ? "↓ ลดเร็ว" : trendDir < 0 ? "↓ ลดลง" : "→ ทรงตัว"}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis
            domain={[yMin, yMax]}
            tick={{ fontSize: 11 }} width={65}
            tickFormatter={(v) => v.toLocaleString()}
            label={{ value: "คะแนน", angle: -90, position: "insideLeft", offset: 10, style: { fontSize: 10, fill: "#aaa" } }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine x={nextYear} stroke="#e94560" strokeDasharray="4 2"
            label={{ value: "คาดการณ์", fontSize: 9, fill: "#e94560" }} />
          <Line type="monotone" dataKey="min" name="ต่ำสุด" stroke="#0f3460" strokeWidth={2} dot={{ r: 4 }} connectNulls={false} />
          <Line type="monotone" dataKey="max" name="สูงสุด" stroke="#aab" strokeWidth={1.5} dot={{ r: 3 }} strokeDasharray="4 2" connectNulls={false} />
          <Line type="monotone" dataKey="trend" name="แนวโน้ม" stroke="#e94560" strokeWidth={1.5} dot={(props) => props.payload.isForecast
            ? <circle cx={props.cx} cy={props.cy} r={5} fill="#e94560" stroke="#fff" strokeWidth={2} />
            : null
          } strokeDasharray="6 3" connectNulls />
        </LineChart>
      </ResponsiveContainer>
      {newSystemData.length >= 2 && reg && lastYear && (
        <div style={s.forecast}>
          คาดการณ์คะแนนต่ำสุด ปี {nextYear} (จากข้อมูลระบบใหม่):{" "}
          <strong style={{ color: "#e94560" }}>{project(reg, nextYear)?.toLocaleString() ?? "–"}</strong>
        </div>
      )}
      {hasOldData && (
        <div style={s.note}>⚠ ซ่อนข้อมูลปี 2020–2022 (ระบบสอบเก่า PAT/O-NET) — ไม่สามารถเปรียบเทียบกับระบบ TGAT/TPAT ได้โดยตรง</div>
      )}
    </div>
  );
}

function ApplicantChart({ data }) {
  const validApp = data.filter((d) => d.year >= NEW_SYSTEM_YEAR && d.applicants != null);
  const reg = linearRegression(validApp.map((d) => ({ x: d.year, y: d.applicants })));
  const lastYear = data[data.length - 1]?.year;
  const nextYear = lastYear + 1;

  const allVals = data.flatMap((d) => [d.applicants, d.accepted].filter(Boolean));
  const yMax = allVals.length ? Math.ceil(Math.max(...allVals) * 1.2 / 10) * 10 : 100;

  const chartData = [
    ...data,
    {
      year: nextYear,
      applicants: null,
      accepted: null,
      forecast: project(reg, nextYear),
      isForecast: true,
    },
  ];

  const trendDir = reg ? reg.slope : 0;
  const forecastVal = project(reg, nextYear);

  return (
    <div style={{ marginTop: 16 }}>
      <div style={s.chartHeader}>
        <span style={s.chartLabel}>จำนวนผู้สมัครและผู้ได้รับคัดเลือก (คน)</span>
        {reg && (
          <span style={{ ...s.badge, background: trendDir > 0 ? "#fee" : trendDir < 0 ? "#efe" : "#f5f5f5",
            color: trendDir > 0 ? "#c33" : trendDir < 0 ? "#0a7" : "#888" }}>
            {trendDir > 0 ? "↑ ผู้สมัครเพิ่มขึ้น" : trendDir < 0 ? "↓ ผู้สมัครลดลง" : "→ ทรงตัว"}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis domain={[0, yMax]} tick={{ fontSize: 11 }} width={55}
            tickFormatter={(v) => v.toLocaleString()}
            label={{ value: "คน", angle: -90, position: "insideLeft", offset: 10, style: { fontSize: 10, fill: "#aaa" } }}
          />
          <Tooltip content={<CustomTooltip suffix="คน" />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine x={nextYear} stroke="#e94560" strokeDasharray="4 2" />
          <Bar dataKey="applicants" name="ผู้สมัคร" fill="#0f3460" radius={[4, 4, 0, 0]} />
          <Bar dataKey="accepted" name="รับจริง" fill="#0a7" radius={[4, 4, 0, 0]} />
          <Bar dataKey="forecast" name="คาดการณ์ผู้สมัคร" fill="#e94560" radius={[4, 4, 0, 0]} opacity={0.6} />
        </BarChart>
      </ResponsiveContainer>
      {forecastVal != null && (
        <div style={s.forecast}>
          คาดการณ์ผู้สมัคร ปี {nextYear}:{" "}
          <strong style={{ color: "#e94560" }}>{forecastVal.toLocaleString()} คน</strong>
          {validApp.length && validApp[validApp.length - 1]?.accepted
            ? ` (อัตราการแข่งขันคาด ${(forecastVal / validApp[validApp.length - 1].accepted).toFixed(1)}:1)`
            : ""}
        </div>
      )}

      {/* Year-by-year stats */}
      <div style={s.yearStats}>
        {data.filter((d) => d.applicants).map((d) => (
          <div key={d.year} style={s.yearRow}>
            <span style={s.yearLabel}>ปี {d.year}</span>
            <span>ผู้สมัคร <strong>{d.applicants?.toLocaleString()}</strong></span>
            <span>รับ <strong>{d.accepted?.toLocaleString() ?? "–"}</strong></span>
            {d.applicants && d.accepted && (
              <span style={{ color: "#e94560" }}>
                {(d.applicants / d.accepted).toFixed(1)}:1
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

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

  if (loading) return <div style={s.placeholder}>กำลังโหลดข้อมูลสถิติย้อนหลัง...</div>;
  if (!data || data.length === 0) return <div style={s.placeholder}>ไม่มีข้อมูลสถิติย้อนหลัง</div>;

  const hasOldData = data.some((d) => d.year < NEW_SYSTEM_YEAR);

  // Only display new-system data (2023+) in the charts
  const newData = data.filter((d) => d.year >= NEW_SYSTEM_YEAR);

  const scoreData = newData.map((d) => ({
    year: d.year,
    min: d.min_admitted_score,
    max: d.max_admitted_score,
  }));

  const applicantData = newData.map((d) => ({
    year: d.year,
    applicants: d.applicants_count,
    accepted: d.accepted_count,
  }));

  const hasApplicantData = applicantData.some((d) => d.applicants != null);
  const hasScoreData = scoreData.some((d) => d.min != null);

  return (
    <div style={s.container}>
      <div style={s.sectionTitle}>สถิติย้อนหลัง {data[0].year}–{data[data.length - 1].year}</div>
      {hasScoreData && <ScoreChart data={scoreData} />}
      {hasApplicantData && <ApplicantChart data={applicantData} />}
    </div>
  );
}

const s = {
  container: { marginTop: 12, background: "#f8f9ff", borderRadius: 8, padding: "10px 12px" },
  sectionTitle: { fontWeight: 700, fontSize: "0.88rem", color: "#1a1a2e", marginBottom: 10 },
  chartHeader: { display: "flex", alignItems: "center", gap: 8, marginBottom: 4 },
  chartLabel: { fontSize: "0.82rem", fontWeight: 600, color: "#444" },
  badge: { fontSize: "0.75rem", fontWeight: 600, padding: "2px 8px", borderRadius: 12 },
  forecast: { fontSize: "0.82rem", color: "#555", marginTop: 4, textAlign: "right" },
  placeholder: { color: "#aaa", fontSize: "0.85rem", padding: "12px 0", textAlign: "center" },
  note: { fontSize: "0.75rem", color: "#e6a817", marginTop: 4, background: "#fffbeb", borderRadius: 6, padding: "4px 8px" },
  yearStats: { marginTop: 8, borderTop: "1px solid #eee", paddingTop: 8 },
  yearRow: {
    display: "flex", gap: 16, fontSize: "0.82rem", color: "#555",
    padding: "3px 0", flexWrap: "wrap",
  },
  yearLabel: { fontWeight: 600, color: "#333", minWidth: 55 },
};
