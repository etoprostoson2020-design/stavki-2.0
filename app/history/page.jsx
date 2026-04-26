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
    <div style={{ minHeight: "100vh", background: "#0a0e1a", color: "#e8eaf0", fontFamily: "'DM Mono','Courier New',monospace" }}>
      <header style={{
        background: "linear-gradient(135deg,#0d1b2a 0%,#1a0a2e 50%,#0d1b2a 100%)",
        borderBottom: "1px solid #1e3a5f",
        padding: "28px 24px",
      }}>
        <div style={{ maxWidth: "860px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px" }}>
          <div>
            <div style={{ fontSize: "10px", letterSpacing: "3px", color: "#00c8ff", textTransform: "uppercase", marginBottom: "6px" }}>
              Analysis History
            </div>
            <h1 style={{ margin: 0, fontSize: "22px", fontWeight: "800", fontFamily: "'Arial Black',Impact,sans-serif", color: "#e8eaf0" }}>
              SAVED ANALYSES
            </h1>
          </div>
          <Link href="/" style={{ textDecoration: "none" }}>
            <div style={{ background: "rgba(0,200,255,0.08)", border: "1px solid rgba(0,200,255,0.25)", borderRadius: "6px", padding: "8px 16px", fontSize: "11px", letterSpacing: "1px", color: "#00c8ff", textTransform: "uppercase" }}>
              ← New Analysis
            </div>
          </Link>
        </div>
      </header>

      <main style={{ maxWidth: "860px", margin: "0 auto", padding: "32px 16px" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "40px", color: "#2a4a5a", fontSize: "12px", letterSpacing: "2px", textTransform: "uppercase" }}>
            Loading...
          </div>
        ) : (
          <HistoryList items={items} onDelete={handleDelete} />
        )}
      </main>
    </div>
  );
}
