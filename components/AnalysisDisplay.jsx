"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function AnalysisDisplay({ text, loading }) {
  if (loading && !text) {
    return (
      <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "16px", padding: "60px 20px", textAlign: "center", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
        <div style={{ fontSize: "32px", marginBottom: "14px", animation: "pulse 1.5s infinite" }}>⚡</div>
        <div style={{ fontSize: "13px", fontWeight: "600", color: "#64748b", marginBottom: "6px" }}>
          Загружаю коэффициенты и анализирую...
        </div>
        <div style={{ fontSize: "12px", color: "#94a3b8" }}>Обычно занимает 15–30 секунд</div>
      </div>
    );
  }

  if (!text) return null;

  return (
    <div style={{
      background: "#ffffff",
      border: "1px solid #e2e8f0",
      borderRadius: "16px",
      padding: "28px",
      fontSize: "14px",
      lineHeight: "1.75",
      boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
    }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {text}
      </ReactMarkdown>
      {loading && (
        <span style={{ display: "inline-block", width: "8px", height: "15px", background: "#0ea5e9", marginLeft: "2px", verticalAlign: "middle", animation: "blink 0.9s step-end infinite" }} />
      )}
    </div>
  );
}

const mdComponents = {
  h2: ({ children }) => (
    <h2 style={{ color: "#0ea5e9", fontSize: "16px", fontWeight: "700", margin: "24px 0 10px", borderBottom: "1px solid #e2e8f0", paddingBottom: "8px" }}>{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ color: "#7c3aed", fontSize: "14px", fontWeight: "700", margin: "18px 0 8px" }}>{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 style={{ color: "#0f172a", fontSize: "14px", fontWeight: "700", margin: "14px 0 6px" }}>{children}</h4>
  ),
  p: ({ children }) => <p style={{ color: "#334155", marginBottom: "10px", marginTop: 0 }}>{children}</p>,
  strong: ({ children }) => <strong style={{ color: "#0f172a", fontWeight: "700" }}>{children}</strong>,
  em: ({ children }) => <em style={{ color: "#475569" }}>{children}</em>,
  ul: ({ children }) => <ul style={{ color: "#334155", paddingLeft: "20px", marginBottom: "10px", marginTop: "4px" }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ color: "#334155", paddingLeft: "20px", marginBottom: "10px", marginTop: "4px" }}>{children}</ol>,
  li: ({ children }) => <li style={{ marginBottom: "4px" }}>{children}</li>,
  hr: () => <hr style={{ border: "none", borderTop: "1px solid #e2e8f0", margin: "20px 0" }} />,
  blockquote: ({ children }) => (
    <blockquote style={{ borderLeft: "3px solid #0ea5e9", paddingLeft: "14px", margin: "10px 0", color: "#475569" }}>{children}</blockquote>
  ),
  table: ({ children }) => (
    <div style={{ overflowX: "auto", marginBottom: "20px", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px", minWidth: "500px" }}>{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead>{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr>{children}</tr>,
  th: ({ children }) => (
    <th style={{ border: "1px solid #e2e8f0", padding: "10px 14px", background: "#f0f9ff", color: "#0ea5e9", fontSize: "12px", fontWeight: "700", textAlign: "left", whiteSpace: "nowrap" }}>{children}</th>
  ),
  td: ({ children }) => (
    <td style={{ border: "1px solid #e2e8f0", padding: "10px 14px", color: "#334155", verticalAlign: "middle", whiteSpace: "normal", wordBreak: "break-word" }}>{children}</td>
  ),
  pre: ({ children }) => (
    <pre style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "14px", overflowX: "auto", margin: "10px 0" }}>{children}</pre>
  ),
  code: ({ children }) => (
    <code style={{ fontFamily: "monospace", fontSize: "12px", color: "#0ea5e9", background: "#f0f9ff", borderRadius: "3px", padding: "1px 5px" }}>{children}</code>
  ),
};
