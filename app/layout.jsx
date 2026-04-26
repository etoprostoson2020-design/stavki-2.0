export const metadata = {
  title: "Sports Betting Analyst Prompt",
  description: "A structured AI prompt that turns Claude into a professional sports betting analyst with live web search and value calculation.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0 }}>{children}</body>
    </html>
  );
}
