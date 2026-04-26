"use client";

import { useRouter } from "next/navigation";

export default function HistoryList({ items, onDelete }) {
  const router = useRouter();

  if (!items.length) {
    return (
      <div style={{ textAlign: "center", padding: "40px", color: "#2a4a5a" }}>
        <div style={{ fontSize: "11px", letterSpacing: "2px", textTransform: "uppercase" }}>No analyses yet</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {items.map((item) => (
        <div
          key={item.id}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: "8px",
            padding: "14px 16px",
            cursor: "pointer",
            transition: "border-color 0.2s",
          }}
          onClick={() => router.push(`/history/${item.id}`)}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = "rgba(0,200,255,0.25)")}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)")}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: "13px", color: "#c8daea", fontWeight: "600", marginBottom: "3px" }}>
              {item.homeTeam} vs {item.awayTeam}
            </div>
            <div style={{ fontSize: "11px", color: "#4a6a8a", display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <span>{item.league}</span>
              <span>{formatDate(item.matchDate)}</span>
              <span style={{ color: "#2a4a5a" }}>Saved: {formatCreated(item.createdAt)}</span>
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete(item.id);
            }}
            style={{
              background: "transparent",
              border: "1px solid rgba(255,80,80,0.2)",
              borderRadius: "5px",
              padding: "5px 10px",
              color: "rgba(255,80,80,0.5)",
              fontSize: "11px",
              cursor: "pointer",
              fontFamily: "inherit",
              flexShrink: 0,
              transition: "all 0.2s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = "rgba(255,80,80,0.6)";
              e.currentTarget.style.color = "rgba(255,80,80,0.9)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "rgba(255,80,80,0.2)";
              e.currentTarget.style.color = "rgba(255,80,80,0.5)";
            }}
          >
            Delete
          </button>
        </div>
      ))}
    </div>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function formatCreated(dateStr) {
  return new Date(dateStr).toLocaleDateString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
  });
}
