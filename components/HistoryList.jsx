"use client";

import { useRouter } from "next/navigation";

export default function HistoryList({ items, onDelete }) {
  const router = useRouter();

  if (!items.length) {
    return (
      <div style={{ textAlign: "center", padding: "60px", color: "#94a3b8" }}>
        <div style={{ fontSize: "14px" }}>Анализов пока нет</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      {items.map((item) => (
        <div
          key={item.id}
          onClick={() => router.push(`/history/${item.id}`)}
          style={{
            background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "12px",
            padding: "16px 20px", display: "flex", alignItems: "center", gap: "16px",
            cursor: "pointer", transition: "box-shadow 0.2s", boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
            flexWrap: "wrap",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.1)")}
          onMouseLeave={(e) => (e.currentTarget.style.boxShadow = "0 1px 3px rgba(0,0,0,0.04)")}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: "15px", fontWeight: "700", color: "#0f172a", marginBottom: "4px" }}>
              {item.homeTeam} — {item.awayTeam}
            </div>
            <div style={{ fontSize: "12px", color: "#94a3b8", display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <span>{item.league}</span>
              <span>{item.matchDate}</span>
              <span>Сохранено: {new Date(item.createdAt).toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" })}</span>
            </div>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(item.id); }}
            style={{
              background: "transparent", border: "1px solid #fecaca", borderRadius: "8px",
              padding: "6px 12px", color: "#f87171", fontSize: "12px",
              cursor: "pointer", fontFamily: "inherit", flexShrink: 0, transition: "all 0.2s",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "#fef2f2"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
          >
            Удалить
          </button>
        </div>
      ))}
    </div>
  );
}
