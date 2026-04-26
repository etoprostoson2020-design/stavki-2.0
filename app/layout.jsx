export const metadata = {
  title: "Sports Betting Analyst",
  description: "AI-powered sports betting analysis with live odds and web search.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0 }}>{children}</body>
    </html>
  );
}
