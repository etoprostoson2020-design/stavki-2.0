"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import HistoryList from "@/components/HistoryList";

export default function HistoryPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/history")
      .then((r) => r.json())
      .then((data) => { setItems(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const handleDelete = async (id) => {
    await fetch(`/api/history/${id}`, { method: "DELETE" });
    setItems((prev) => prev.filter((i) => i.id !== id));
  };

  return (
    <div style={{ minHeight: "100vh", background: "#f0f4f8", fontFamily: "'Inter','Segoe UI',sans-serif", color: "#0f172a" }}>
      <header style={{
        background: "linear-gradient(135deg,#0f172a 0%,#1e1040 50%,#0f172a 100%)",
        padding: "24px",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px",
      }}>
        <div>
          <div style={{ fontSize: "11px", letterSpacing: "3px", color: "#38bdf8", textTransform: "uppercase", marginBottom: "4px" }}>
            История анализов
          </div>
          <h1 style={{ margin: 0, fontSize: "22px", fontWeight: "800", color: "#ffffff" }}>
            Сохранённые анализы
          </h1>
        </div>
        <Link href="/" style={{ textDecoration: "none" }}>
          <div style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: "8px", padding: "8px 16px", fontSize: "13px", color: "#94a3b8" }}>
            ← Новый анализ
          </div>
        </Link>
      </header>

      <main style={{ maxWidth: "900px", margin: "0 auto", padding: "32px 16px" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "60px", color: "#94a3b8", fontSize: "14px" }}>Загрузка...</div>
        ) : (
          <HistoryList items={items} onDelete={handleDelete} />
        )}
      </main>
    </div>
  );
}
