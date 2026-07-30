import './globals.css';

export const metadata = {
  title: 'TestAI Platform',
  description: 'AI驱动的测试工具平台',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}