"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import AnalysisDisplay from "@/components/AnalysisDisplay";

export default function AnalysisPage() {
  const { id } = useParams();
  const router = useRouter();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/history/${id}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [id]);

  const handleDelete = async () => {
    await fetch(`/api/history/${id}`, { method: "DELETE" });
    router.push("/history");
  };

  return (
    <div style={{ minHeight: "100vh", background: "#f0f4f8", fontFamily: "'Inter','Segoe UI',sans-serif", color: "#0f172a" }}>
      <header style={{
        background: "linear-gradient(135deg,#0f172a 0%,#1e1040 50%,#0f172a 100%)",
        padding: "24px",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px",
      }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "11px", letterSpacing: "3px", color: "#38bdf8", textTransform: "uppercase", marginBottom: "4px" }}>
            Сохранённый анализ
          </div>
          {data && (
            <h1 style={{ margin: 0, fontSize: "clamp(14px,3vw,22px)", fontWeight: "800", color: "#ffffff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {data.homeTeam} — {data.awayTeam}
            </h1>
          )}
        </div>
        <div style={{ display: "flex", gap: "8px", flexShrink: 0 }}>
          <Link href="/history" style={{ textDecoration: "none" }}>
            <div style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: "8px", padding: "8px 14px", fontSize: "13px", color: "#94a3b8" }}>
              ← История
            </div>
          </Link>
          <button
            onClick={handleDelete}
            style={{ background: "transparent", border: "1px solid rgba(248,113,113,0.4)", borderRadius: "8px", padding: "8px 14px", fontSize: "13px", color: "#f87171", cursor: "pointer", fontFamily: "inherit" }}
          >
            Удалить
          </button>
        </div>
      </header>

      <main style={{ maxWidth: "900px", margin: "0 auto", padding: "32px 16px" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "60px", color: "#94a3b8", fontSize: "14px" }}>Загрузка...</div>
        ) : data ? (
          <>
            <div style={{ display: "flex", gap: "10px", marginBottom: "20px", flexWrap: "wrap" }}>
              {[
                { label: "Лига", value: data.league },
                { label: "Дата матча", value: data.matchDate },
                { label: "Сохранено", value: new Date(data.createdAt).toLocaleString("ru-RU") },
              ].map((m, i) => (
                <div key={i} style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "8px 14px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)" }}>
                  <div style={{ fontSize: "10px", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "2px" }}>{m.label}</div>
                  <div style={{ fontSize: "13px", color: "#0f172a", fontWeight: "600" }}>{m.value}</div>
                </div>
              ))}
            </div>
            <AnalysisDisplay text={data.result} loading={false} />
          </>
        ) : (
          <div style={{ textAlign: "center", padding: "60px", color: "#94a3b8" }}>Анализ не найден.</div>
        )}
      </main>

      <style>{`@keyframes blink{0%,100%{opacity:1}50%{opacity:0}} @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}`}</style>
    </div>
  );
}
