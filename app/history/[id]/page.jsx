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
    <div style={{ minHeight: "100vh", background: "#0a0e1a", color: "#e8eaf0", fontFamily: "'DM Mono','Courier New',monospace" }}>
      <header style={{
        background: "linear-gradient(135deg,#0d1b2a 0%,#1a0a2e 50%,#0d1b2a 100%)",
        borderBottom: "1px solid #1e3a5f",
        padding: "28px 24px",
      }}>
        <div style={{ maxWidth: "860px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: "10px", letterSpacing: "3px", color: "#00c8ff", textTransform: "uppercase", marginBottom: "6px" }}>
              Saved Analysis
            </div>
            {data && (
              <h1 style={{ margin: 0, fontSize: "clamp(14px,3vw,22px)", fontWeight: "800", fontFamily: "'Arial Black',Impact,sans-serif", color: "#e8eaf0", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {data.homeTeam} vs {data.awayTeam}
              </h1>
            )}
          </div>
          <div style={{ display: "flex", gap: "8px", flexShrink: 0 }}>
            <Link href="/history" style={{ textDecoration: "none" }}>
              <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "6px", padding: "8px 14px", fontSize: "11px", letterSpacing: "1px", color: "#4a6a8a", textTransform: "uppercase", cursor: "pointer" }}>
                ← History
              </div>
            </Link>
            <button
              onClick={handleDelete}
              style={{ background: "transparent", border: "1px solid rgba(255,60,60,0.25)", borderRadius: "6px", padding: "8px 14px", fontSize: "11px", letterSpacing: "1px", color: "rgba(255,60,60,0.6)", textTransform: "uppercase", cursor: "pointer", fontFamily: "inherit" }}
            >
              Delete
            </button>
          </div>
        </div>
      </header>

      <main style={{ maxWidth: "860px", margin: "0 auto", padding: "32px 16px" }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "40px", color: "#2a4a5a", fontSize: "12px", letterSpacing: "2px", textTransform: "uppercase" }}>
            Loading...
          </div>
        ) : data ? (
          <>
            <div style={{ display: "flex", gap: "16px", marginBottom: "20px", flexWrap: "wrap" }}>
              {[
                { label: "League", value: data.league },
                { label: "Match date", value: data.matchDate },
                { label: "Saved", value: new Date(data.createdAt).toLocaleString("en-GB") },
              ].map((m, i) => (
                <div key={i} style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)", borderRadius: "6px", padding: "8px 14px" }}>
                  <div style={{ fontSize: "9px", letterSpacing: "2px", color: "#2a4a5a", textTransform: "uppercase", marginBottom: "3px" }}>{m.label}</div>
                  <div style={{ fontSize: "12px", color: "#8fa8bf" }}>{m.value}</div>
                </div>
              ))}
            </div>
            <AnalysisDisplay text={data.result} loading={false} />
          </>
        ) : (
          <div style={{ textAlign: "center", padding: "40px", color: "#2a4a5a" }}>Analysis not found.</div>
        )}
      </main>
    </div>
  );
}
