import { useState, useEffect } from "react";
import { t } from "../theme";

const CATEGORIES = [
  { id: "stem",   label: "วิทย์ & วิศวะ",    cx: 108, cy: 145, r: 90, fill: "#4a7a4c", glow: "rgba(74,122,76,.25)"   },
  { id: "tech",   label: "เทคโนโลยี & IT",   cx: 295, cy: 110, r: 78, fill: "#b86e42", glow: "rgba(184,110,66,.25)"  },
  { id: "biz",    label: "ธุรกิจ & การเงิน", cx: 452, cy: 150, r: 68, fill: "#b8923a", glow: "rgba(184,146,58,.25)"  },
  { id: "health", label: "สุขภาพ & แพทย์",  cx: 600, cy: 100, r: 64, fill: "#4a7a8a", glow: "rgba(74,122,138,.25)"  },
  { id: "law",    label: "กฎหมาย",           cx: 215, cy: 248, r: 46, fill: "#8a4040", glow: "rgba(138,64,64,.25)"   },
  { id: "arts",   label: "ศิลปะ & ออกแบบ",  cx: 388, cy: 252, r: 50, fill: "#7a5a96", glow: "rgba(122,90,150,.25)"  },
  { id: "edu",    label: "การศึกษา",         cx: 536, cy: 248, r: 43, fill: "#5c8a5e", glow: "rgba(92,138,94,.25)"   },
  { id: "media",  label: "สื่อ & สังคม",    cx: 688, cy: 210, r: 52, fill: "#8a6a3a", glow: "rgba(138,106,58,.25)"  },
];

// Monotone SVG icons, normalized to ±10 coordinate system
function BubbleIcon({ id, sz, opacity }) {
  const sc = sz / 20;
  const sw = 36 / sz; // stroke stays ~1.8px after scaling
  const lc = { strokeLinecap: "round", strokeLinejoin: "round" };
  const S = (extra = {}) => ({ fill: "none", stroke: "white", strokeWidth: sw, ...lc, ...extra });
  const F = { fill: "white", stroke: "none" };

  const icon = {
    stem: (
      <>
        <ellipse {...S()} rx="9" ry="3.5" />
        <ellipse {...S()} rx="9" ry="3.5" transform="rotate(60)" />
        <ellipse {...S()} rx="9" ry="3.5" transform="rotate(120)" />
        <circle {...F} r="2.2" />
      </>
    ),
    tech: (
      <>
        <polyline {...S()} points="-6,-8 -11,0 -6,8" />
        <polyline {...S()} points="6,-8 11,0 6,8" />
        <line {...S()} x1="-2" y1="7" x2="2" y2="-7" />
      </>
    ),
    biz: (
      <>
        <rect {...F} x="-10" y="-1" width="5" height="11" rx="1" opacity="0.6" />
        <rect {...F} x="-2.5" y="-9" width="5" height="19" rx="1" />
        <rect {...F} x="5" y="-5" width="5" height="15" rx="1" opacity="0.6" />
        <line {...S()} x1="-11" y1="10" x2="11" y2="10" />
      </>
    ),
    health: (
      <>
        <rect {...F} x="-2.8" y="-10" width="5.6" height="20" rx="1.5" />
        <rect {...F} x="-10" y="-2.8" width="20" height="5.6" rx="1.5" />
      </>
    ),
    law: (
      <>
        <line {...S()} x1="0" y1="-10" x2="0" y2="8" />
        <line {...S()} x1="-9" y1="-2" x2="9" y2="-2" />
        <line {...S()} x1="-9" y1="-2" x2="-11" y2="5" />
        <line {...S()} x1="9" y1="-2" x2="11" y2="5" />
        <circle {...S()} cx="-11" cy="7.5" r="2.5" />
        <circle {...S()} cx="11" cy="7.5" r="2.5" />
      </>
    ),
    arts: (
      <>
        <path {...S()} d="M0,-11 L11,0 L0,11 L-11,0 Z" />
        <circle {...F} r="2.5" />
      </>
    ),
    edu: (
      <>
        <path {...S()} d="M-10,0 L0,-7 L10,0 L0,7 Z" />
        <path {...S()} d="M-7,4 L-7,10 Q0,14 7,10 L7,4" />
        <line {...S()} x1="10" y1="0" x2="10" y2="-6" />
        <circle {...F} cx="10" cy="-7.5" r="1.8" />
      </>
    ),
    media: (
      <>
        <circle {...F} cy="7" r="2.5" />
        <path {...S()} d="M-5,3.5 A6.5,6.5 0 0,1 5,3.5" />
        <path {...S({ strokeOpacity: 0.75 })} d="M-9,-1 A11.5,11.5 0 0,1 9,-1" />
        <path {...S({ strokeOpacity: 0.45 })} d="M-13,-5 A16,16 0 0,1 13,-5" />
      </>
    ),
  }[id];

  return (
    <g transform={`scale(${sc})`} opacity={opacity}>
      {icon}
    </g>
  );
}

const CATEGORY_KEYWORDS = {
  stem:   ["วิศวกรรม", "วิทยาศาสตร์", "คณิตศาสตร์", "ฟิสิกส์", "เคมี", "engineer", "science"],
  tech:   ["เทคโนโลยี", "ไอที", "ซอฟต์แวร์", "โปรแกรม", "data", "software", "developer", "it"],
  biz:    ["ธุรกิจ", "การเงิน", "การตลาด", "บัญชี", "marketing", "finance", "business"],
  health: ["แพทย์", "พยาบาล", "สุขภาพ", "เภสัช", "ทันต", "health", "medical", "nurse"],
  law:    ["กฎหมาย", "รัฐศาสตร์", "law", "legal", "politics"],
  arts:   ["ศิลปะ", "ออกแบบ", "สถาปัตย์", "ดนตรี", "art", "design"],
  edu:    ["การศึกษา", "ครู", "มนุษยศาสตร์", "ภาษา", "teacher", "education"],
  media:  ["สื่อ", "นิเทศ", "สังคม", "media", "communication", "journalist"],
};

function matchCategory(rec) {
  const text = `${rec.title} ${rec.industry_group || ""}`.toLowerCase();
  for (const [id, keywords] of Object.entries(CATEGORY_KEYWORDS)) {
    if (keywords.some((k) => text.includes(k.toLowerCase()))) return id;
  }
  return null;
}

export default function CareerPathView({ getToken }) {
  const [recs, setRecs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeCategory, setActiveCategory] = useState(null);
  const [hoveredCat, setHoveredCat] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
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
    })();
    return () => controller.abort();
  }, []);

  const filtered = recs
    ? activeCategory
      ? recs.filter((r) => matchCategory(r) === activeCategory)
      : recs
    : [];

  const activeCat = CATEGORIES.find((c) => c.id === activeCategory);

  return (
    <div style={s.page}>
      {/* Header */}
      <div style={s.header}>
        <div style={s.headerLeft}>
          <div style={s.title}>อาชีพแนะนำ</div>
          <div style={s.subtitle}>สำรวจเส้นทางอาชีพตามสาขาที่สนใจ หรือคุยกับ Career Dreamer เพื่อรับคำแนะนำส่วนตัว</div>
        </div>
        {activeCategory && (
          <button style={s.clearBtn} onClick={() => setActiveCategory(null)}>
            ✕ ล้างตัวกรอง
          </button>
        )}
      </div>

      {/* Bubble chart */}
      <div style={s.chartWrap}>
        <div style={s.chartLabel}>คลิกสาขาเพื่อกรองอาชีพ</div>
        <svg
          viewBox="0 0 780 300"
          style={s.svg}
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            {CATEGORIES.map((c) => (
              <radialGradient key={c.id} id={`grad-${c.id}`} cx="40%" cy="35%" r="65%">
                <stop offset="0%" stopColor={c.fill} stopOpacity="0.9" />
                <stop offset="100%" stopColor={c.fill} stopOpacity="0.55" />
              </radialGradient>
            ))}
            {CATEGORIES.map((c) => (
              <filter key={`f-${c.id}`} id={`glow-${c.id}`} x="-30%" y="-30%" width="160%" height="160%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
              </filter>
            ))}
          </defs>

          {CATEGORIES.map((cat) => {
            const isActive = activeCategory === cat.id;
            const isHovered = hoveredCat === cat.id;
            const dim = activeCategory && !isActive;
            const scale = isActive ? 1.08 : isHovered ? 1.05 : 1;
            const iconSize = Math.round(cat.r * 0.38);
            const labelSize = Math.max(10, Math.round(cat.r * 0.175));

            return (
              <g
                key={cat.id}
                transform={`translate(${cat.cx},${cat.cy}) scale(${scale})`}
                style={{ cursor: "pointer", transition: "transform .2s ease", transformOrigin: `${cat.cx}px ${cat.cy}px` }}
                onClick={() => setActiveCategory(isActive ? null : cat.id)}
                onMouseEnter={() => setHoveredCat(cat.id)}
                onMouseLeave={() => setHoveredCat(null)}
              >
                {/* Glow ring when active */}
                {isActive && (
                  <circle r={cat.r + 8} fill="none" stroke={cat.fill} strokeWidth="2" opacity="0.5" />
                )}
                {/* Main circle */}
                <circle
                  r={cat.r}
                  fill={`url(#grad-${cat.id})`}
                  opacity={dim ? 0.25 : 1}
                  stroke={isActive ? cat.fill : "rgba(255,255,255,0.12)"}
                  strokeWidth={isActive ? 2 : 1}
                  filter={isActive || isHovered ? `url(#glow-${cat.id})` : undefined}
                />
                {/* Icon */}
                <g transform={`translate(0,${-labelSize * 0.6})`} opacity={dim ? 0.3 : 1}>
                  <BubbleIcon id={cat.id} sz={iconSize} />
                </g>
                {/* Label */}
                <text
                  x="0" y={iconSize * 0.65 + labelSize * 0.5}
                  textAnchor="middle"
                  fontSize={labelSize}
                  fontWeight={isActive ? "700" : "500"}
                  fill={dim ? "rgba(255,255,255,.3)" : "#fff"}
                  fontFamily="'Sarabun','Inter',sans-serif"
                  style={{ userSelect: "none" }}
                >{cat.label}</text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Career list */}
      <div style={s.listSection}>
        <div style={s.listHeader}>
          {activeCat
            ? <><span style={{ ...s.dot, background: activeCat.fill }} />{activeCat.label}</>
            : "อาชีพทั้งหมด"
          }
          {recs && <span style={s.count}>{filtered.length} อาชีพ</span>}
        </div>

        {loading && <div style={s.hint}>กำลังโหลด...</div>}
        {error   && <div style={{ color: t.fail, padding: "12px 0" }}>{error}</div>}

        {!loading && !error && filtered.length === 0 && (
          <div style={s.empty}>
            <div style={s.emptyIcon}>💼</div>
            <div style={s.emptyTitle}>
              {activeCategory ? `ไม่มีอาชีพในสาขา ${activeCat?.label}` : "ยังไม่มีอาชีพแนะนำ"}
            </div>
            <div style={s.hint}>คุยกับ <strong>Career Dreamer</strong> ในแท็บแชทเพื่อให้ AI วิเคราะห์ความสนใจและจุดแข็งของคุณก่อนนะ</div>
          </div>
        )}

        {!loading && filtered.length > 0 && (
          <div style={s.grid}>
            {filtered.map((rec, i) => <CareerCard key={i} rec={rec} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function CareerCard({ rec }) {
  const [open, setOpen] = useState(false);
  const score = rec.match_score != null ? Math.round(rec.match_score * 100) : null;
  const scoreColor = score >= 80 ? t.pass : score >= 60 ? "#b8923a" : t.text3;
  const catId = matchCategory(rec);
  const cat = CATEGORIES.find((c) => c.id === catId);

  return (
    <div style={{ ...s.card, ...(open ? s.cardOpen : {}) }}>
      <div style={s.cardTop} onClick={() => setOpen(!open)}>
        <div style={s.cardMeta}>
          {cat && (
              <span style={{ ...s.catDot, background: cat.fill }}>
                <svg width="18" height="18" viewBox="-10 -10 20 20" overflow="visible">
                  <BubbleIcon id={cat.id} sz={20} opacity={1} />
                </svg>
              </span>
            )}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={s.cardTitle}>{rec.title}</div>
            {rec.industry_group && <div style={s.cardIndustry}>{rec.industry_group}</div>}
          </div>
          {score !== null && (
            <div style={{ textAlign: "right", flexShrink: 0 }}>
              <div style={{ ...s.scoreNum, color: scoreColor }}>{score}%</div>
              <div style={s.scoreLabel}>เข้ากัน</div>
            </div>
          )}
          <span style={s.chevron}>{open ? "▲" : "▼"}</span>
        </div>

        {/* Score bar */}
        {score !== null && (
          <div style={s.barTrack}>
            <div style={{ ...s.barFill, width: `${score}%`, background: scoreColor }} />
          </div>
        )}

        {rec.avg_salary_thb && (
          <div style={s.salary}>💰 เงินเดือนเฉลี่ย {rec.avg_salary_thb.toLocaleString()} บาท/เดือน</div>
        )}
      </div>

      {open && (
        <div style={s.cardBody}>
          {rec.overview_description && (
            <p style={s.overview}>{rec.overview_description}</p>
          )}
          {rec.ai_reasoning && (
            <div style={s.reasonBox}>
              <div style={s.reasonLabel}>🤖 เหตุผลที่แนะนำ</div>
              <p style={s.reasonText}>{rec.ai_reasoning}</p>
            </div>
          )}
          {Array.isArray(rec.top_skills) && rec.top_skills.length > 0 && (
            <div>
              <div style={s.skillsLabel}>ทักษะที่ต้องการ</div>
              <div style={s.tags}>
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
  page: { padding: "24px 32px", fontFamily: "'Inter','Sarabun',sans-serif", color: t.text1, background: t.bg, minHeight: "100%" },

  header: { display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24, gap: 16 },
  headerLeft: {},
  title:    { fontSize: 22, fontWeight: 800, color: t.text1, marginBottom: 4 },
  subtitle: { fontSize: 14, color: t.text3, lineHeight: 1.6 },
  clearBtn: {
    padding: "7px 14px", border: `1px solid ${t.border}`, borderRadius: 20,
    background: t.surface, color: t.text2, fontSize: 13, cursor: "pointer",
    fontFamily: "inherit", flexShrink: 0, whiteSpace: "nowrap",
  },

  chartWrap: { background: t.surface, border: `1px solid ${t.border}`, borderRadius: 16, padding: "16px 16px 8px", marginBottom: 28 },
  chartLabel: { fontSize: 12, color: t.text3, marginBottom: 6, textAlign: "right" },
  svg: { width: "100%", height: "auto", display: "block", maxHeight: 300 },

  listSection: {},
  listHeader: { display: "flex", alignItems: "center", gap: 8, fontSize: 15, fontWeight: 700, color: t.text1, marginBottom: 16 },
  dot: { width: 10, height: 10, borderRadius: "50%", display: "inline-block", flexShrink: 0 },
  count: { marginLeft: "auto", fontSize: 13, color: t.text3, fontWeight: 400 },

  hint:  { fontSize: 14, color: t.text3, lineHeight: 1.7 },
  empty: { textAlign: "center", padding: "3rem 1rem" },
  emptyIcon:  { fontSize: 48, marginBottom: 12 },
  emptyTitle: { fontSize: 17, fontWeight: 700, color: t.text2, marginBottom: 8 },

  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 14 },

  card: {
    background: t.surface, border: `1px solid ${t.border}`,
    borderRadius: 12, overflow: "hidden", transition: "box-shadow .15s",
  },
  cardOpen: { boxShadow: "0 4px 20px rgba(0,0,0,.06)" },
  cardTop: { padding: "14px 16px", cursor: "pointer" },
  cardMeta: { display: "flex", alignItems: "center", gap: 10, marginBottom: 8 },
  catDot: { width: 32, height: 32, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0 },
  cardTitle:    { fontSize: 16, fontWeight: 700, color: t.text1, marginBottom: 2 },
  cardIndustry: { fontSize: 13, color: t.text3 },
  scoreNum:  { fontSize: 18, fontWeight: 800, lineHeight: 1 },
  scoreLabel:{ fontSize: 11, color: t.text3 },
  chevron:   { fontSize: 11, color: t.text3, marginLeft: 4, flexShrink: 0 },
  barTrack:  { height: 4, background: t.border, borderRadius: 2, marginBottom: 8, overflow: "hidden" },
  barFill:   { height: "100%", borderRadius: 2, transition: "width .4s ease" },
  salary:    { fontSize: 13, color: t.pass, fontWeight: 600 },

  cardBody:   { padding: "14px 16px", borderTop: `1px solid ${t.border}`, background: t.card },
  overview:   { fontSize: 14, color: t.text2, lineHeight: 1.7, marginBottom: 12, marginTop: 0 },
  reasonBox:  { background: t.accentBg, border: `1px solid ${t.border}`, borderRadius: 8, padding: "10px 12px", marginBottom: 12 },
  reasonLabel:{ fontSize: 12, fontWeight: 700, color: t.accent, marginBottom: 5 },
  reasonText: { fontSize: 13, color: t.text2, lineHeight: 1.65, margin: 0 },
  skillsLabel:{ fontSize: 12, fontWeight: 600, color: t.text2, marginBottom: 8 },
  tags:       { display: "flex", flexWrap: "wrap", gap: 6 },
  tag:        { background: t.accentLight, color: t.accent, border: `1px solid ${t.border}`, borderRadius: 20, padding: "3px 10px", fontSize: 12, fontWeight: 500 },
};
