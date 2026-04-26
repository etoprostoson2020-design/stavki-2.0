"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function AnalysisDisplay({ text, loading }) {
  if (loading && !text) {
    return (
      <div style={{ textAlign: "center", padding: "60px 20px", color: "#4a6a8a" }}>
        <div style={{ fontSize: "32px", marginBottom: "16px", animation: "pulse 1.5s infinite" }}>⚡</div>
        <div style={{ fontSize: "12px", letterSpacing: "3px", textTransform: "uppercase", marginBottom: "8px" }}>
          Fetching odds &amp; analyzing...
        </div>
        <div style={{ fontSize: "11px", color: "#2a4a5a" }}>This takes 15–30 seconds</div>
      </div>
    );
  }

  if (!text) return null;

  return (
    <div style={{
      background: "#080d18",
      border: "1px solid #1a2a3a",
      borderRadius: "10px",
      padding: "28px",
      fontSize: "13px",
      lineHeight: "1.75",
    }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {text}
      </ReactMarkdown>
      {loading && (
        <span style={{
          display: "inline-block",
          width: "8px",
          height: "14px",
          background: "#00c8ff",
          marginLeft: "2px",
          verticalAlign: "middle",
          animation: "blink 0.9s step-end infinite",
        }} />
      )}
    </div>
  );
}

const mdComponents = {
  h2: ({ children }) => (
    <h2 style={{ color: "#00c8ff", fontSize: "15px", fontWeight: "700", margin: "24px 0 10px", borderBottom: "1px solid #1a2a3a", paddingBottom: "8px" }}>
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ color: "#bf5fff", fontSize: "13px", fontWeight: "700", margin: "18px 0 8px", letterSpacing: "0.5px" }}>
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 style={{ color: "#e8eaf0", fontSize: "13px", fontWeight: "700", margin: "14px 0 6px" }}>
      {children}
    </h4>
  ),
  p: ({ children }) => (
    <p style={{ color: "#8fa8bf", marginBottom: "10px", marginTop: 0 }}>{children}</p>
  ),
  strong: ({ children }) => (
    <strong style={{ color: "#c8daea", fontWeight: "700" }}>{children}</strong>
  ),
  em: ({ children }) => (
    <em style={{ color: "#7a9ab5" }}>{children}</em>
  ),
  ul: ({ children }) => (
    <ul style={{ color: "#8fa8bf", paddingLeft: "20px", marginBottom: "10px", marginTop: "4px" }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ color: "#8fa8bf", paddingLeft: "20px", marginBottom: "10px", marginTop: "4px" }}>{children}</ol>
  ),
  li: ({ children }) => (
    <li style={{ marginBottom: "4px" }}>{children}</li>
  ),
  hr: () => (
    <hr style={{ border: "none", borderTop: "1px solid #1a2a3a", margin: "20px 0" }} />
  ),
  blockquote: ({ children }) => (
    <blockquote style={{ borderLeft: "2px solid #00c8ff", paddingLeft: "14px", margin: "10px 0", color: "#6a8aaa" }}>
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div style={{ overflowX: "auto", marginBottom: "14px" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead>{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr>{children}</tr>,
  th: ({ children }) => (
    <th style={{
      border: "1px solid #1e3a5f",
      padding: "8px 12px",
      background: "rgba(0,200,255,0.06)",
      color: "#00c8ff",
      fontSize: "10px",
      letterSpacing: "1px",
      textTransform: "uppercase",
      textAlign: "left",
      fontWeight: "700",
    }}>
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td style={{
      border: "1px solid #1a2a3a",
      padding: "8px 12px",
      color: "#8fa8bf",
    }}>
      {children}
    </td>
  ),
  pre: ({ children }) => (
    <pre style={{
      background: "rgba(0,0,0,0.4)",
      border: "1px solid #1a2a3a",
      borderRadius: "6px",
      padding: "14px",
      overflowX: "auto",
      margin: "10px 0",
    }}>
      {children}
    </pre>
  ),
  code: ({ children }) => (
    <code style={{
      fontFamily: "monospace",
      fontSize: "12px",
      color: "#00c8ff",
      background: "rgba(0,200,255,0.06)",
      borderRadius: "3px",
      padding: "1px 5px",
    }}>
      {children}
    </code>
  ),
};
