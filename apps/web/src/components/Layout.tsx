import { useState } from 'react';
import {
  LayoutDashboard,
  Settings,
  GitBranch,
  Activity,
  Cog,
  Menu,
  X,
  Users,
  UsersRound,
} from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
  { label: '仪表盘', href: '/', icon: LayoutDashboard },
  { label: '治理流程', href: '/governance', icon: GitBranch },
  { label: '工作流', href: '/workflow', icon: Activity },
  { label: '监控告警', href: '/monitoring', icon: Settings },
  { label: '用户管理', href: '/users', icon: Users },
  { label: '团队管理', href: '/teams', icon: UsersRound },
  { label: '系统配置', href: '/config', icon: Cog },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const pathname = usePathname();

  return (
    <div className="flex h-screen bg-gray-50">
      <aside
        className={`${
          sidebarOpen ? 'w-64' : 'w-20'
        } bg-slate-800 text-white transition-all duration-300 flex flex-col`}
      >
        <div className="p-4 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center">
              <span className="text-xl font-bold">T</span>
            </div>
            {sidebarOpen && (
              <div>
                <h1 className="text-lg font-bold">TestAI</h1>
                <p className="text-xs text-slate-400">AI 测试平台</p>
              </div>
            )}
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-300 hover:bg-slate-700 hover:text-white'
                }`}
              >
                <Icon className="w-5 h-5" />
                {sidebarOpen && <span>{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="p-4 border-t border-slate-700 hover:bg-slate-700 transition-colors"
        >
          {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </aside>

      <main className="flex-1 overflow-auto">
        <header className="bg-white shadow-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-gray-800">
                {navItems.find((item) => item.href === pathname)?.label || '仪表盘'}
              </h2>
              <p className="text-sm text-gray-500">
                {new Date().toLocaleDateString('zh-CN', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </p>
            </div>
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                <span className="text-blue-600 font-semibold">A</span>
              </div>
            </div>
          </div>
        </header>
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}