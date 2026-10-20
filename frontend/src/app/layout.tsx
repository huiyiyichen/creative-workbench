import type { Metadata } from 'next';
import { Barlow_Semi_Condensed, DM_Sans, DM_Mono, Noto_Sans_SC, Noto_Serif_SC } from 'next/font/google';
import './globals.css';
import '@/design/tokens.css';
import '@/design/cw.css';
import { THEME_BOOT_SCRIPT } from '@/design/theme-boot';
import ClientLayout from '@/components/ClientLayout';
import SkipToContent from '@/components/SkipToContent';
import { prefetchInitialData } from '@/lib/server-prefetch';

const dmSans = DM_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-dm-sans',
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  display: 'swap',
  variable: '--font-dm-mono',
});

// 衬线 display 字体：用于页面大标题，与 DM Sans body 形成对比，
// 强化「编辑 / 出版物」气质，跳出 sans 后台的售货员感。
const notoSerif = Noto_Serif_SC({
  subsets: ['latin'],
  weight: ['600', '700', '900'],
  display: 'swap',
  variable: '--font-display',
});

// 调色台界面字体（12.2）：正文 Noto Sans SC，数字 Barlow Semi Condensed（OFL，随构建自托管）；
// Windows 上数字优先用系统 Bahnschrift（见 design/tokens.css 的 --cw-num）。
const notoSans = Noto_Sans_SC({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  preload: false,
  variable: '--font-noto-sans-sc',
});

const barlow = Barlow_Semi_Condensed({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  display: 'swap',
  variable: '--font-barlow-sc',
});

export const metadata: Metadata = {
  title: '创意工作台 · AI 创作空间',
  description: '面向创作者的选题、成稿与成片工作台',
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // SSR 预取首屏数据（auth/me + feature-flags + 侧边栏计数），
  // 消除客户端 useEffect 串行拉取导致的白屏。
  // 后端不可达时返回 null，客户端 Provider 会 fallback 到 useEffect。
  const initialData = await prefetchInitialData();

  return (
    <html lang="zh-CN" className={`${dmSans.variable} ${dmMono.variable} ${notoSerif.variable} ${notoSans.variable} ${barlow.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <SkipToContent />
        <ClientLayout initialData={initialData}>{children}</ClientLayout>
      </body>
    </html>
  );
}
