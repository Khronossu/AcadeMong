export default function Icon({ name, size = 20, color = "currentColor" }) {
  const p = { fill: "none", stroke: color, strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" };

  const icons = {
    graduation: (
      <>
        <polygon {...p} points="12,4 22,10 12,16 2,10" />
        <path {...p} d="M7,13.5 L7,19 Q12,22 17,19 L17,13.5" />
        <line {...p} x1="22" y1="10" x2="22" y2="16" />
      </>
    ),
    star: (
      <path
        fill={color} stroke="none"
        d="M12,2 L14.65,8.36 L21.51,8.91 L16.28,13.39 L17.88,20.09 L12,16.5 L6.12,20.09 L7.72,13.39 L2.49,8.91 L9.35,8.36 Z"
      />
    ),
    chat: (
      <path {...p} d="M4,4 Q4,2 6,2 L18,2 Q20,2 20,4 L20,14 Q20,16 18,16 L13,16 L9,21 L9,16 L6,16 Q4,16 4,14 Z" />
    ),
    person: (
      <>
        <circle {...p} cx="12" cy="7" r="4" />
        <path {...p} d="M4,21 C4,15.5 7.5,12 12,12 C16.5,12 20,15.5 20,21" />
      </>
    ),
    "check-circle": (
      <>
        <circle {...p} cx="12" cy="12" r="10" />
        <polyline {...p} points="7,12.5 10,15.5 17,9" />
      </>
    ),
    bookmark: (
      <path {...p} d="M6,2 L18,2 Q19.5,2 19.5,3.5 L19.5,22 L12,17 L4.5,22 L4.5,3.5 Q4.5,2 6,2 Z" />
    ),
    briefcase: (
      <>
        <rect {...p} x="2" y="9" width="20" height="13" rx="2" />
        <path {...p} d="M8,9 L8,5 Q8,2 12,2 Q16,2 16,5 L16,9" />
        <line {...p} x1="2" y1="14" x2="22" y2="14" />
      </>
    ),
    trash: (
      <>
        <rect {...p} x="3" y="7" width="18" height="15" rx="2" />
        <line {...p} x1="1" y1="7" x2="23" y2="7" />
        <path {...p} d="M9,7 L9,4 Q9,2 12,2 Q15,2 15,4 L15,7" />
        <line {...{ ...p, strokeWidth: 1.5 }} x1="9" y1="11" x2="9" y2="18" />
        <line {...{ ...p, strokeWidth: 1.5 }} x1="12" y1="11" x2="12" y2="18" />
        <line {...{ ...p, strokeWidth: 1.5 }} x1="15" y1="11" x2="15" y2="18" />
      </>
    ),
    warning: (
      <>
        <path {...p} d="M12,3 L22,20 L2,20 Z" />
        <line {...{ ...p, strokeWidth: 2 }} x1="12" y1="9" x2="12" y2="14" />
        <circle cx="12" cy="17.5" r="1.3" fill={color} stroke="none" />
      </>
    ),
    gear: (
      <>
        <circle {...p} cx="12" cy="12" r="4" />
        <circle
          fill="none" stroke={color} strokeWidth={5.5} strokeDasharray="3.5 3.6"
          cx="12" cy="12" r="9"
        />
      </>
    ),
    hourglass: (
      <>
        <path {...p} d="M5,2 L19,2 L12,12 L19,22 L5,22 L12,12 Z" />
        <path fill={color} fillOpacity="0.3" stroke="none" d="M5,22 L19,22 L12,12 Z" />
      </>
    ),
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      style={{ display: "inline-block", verticalAlign: "middle", flexShrink: 0 }}
    >
      {icons[name]}
    </svg>
  );
}
