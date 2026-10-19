/** @type {import('next').NextConfig} */
const path = require('path');

const backendApiUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8102';

const nextConfig = {
  // Keep the one-click runtime separate from the developer's build/cache.
  distDir: (process.env.WORKBENCH_LOCAL_BUILD || process.env.CREATIVE_WORKBENCH_LOCAL_BUILD) === '1' ? '.next-local' : '.next',
  reactStrictMode: true,
  compress: true,
  poweredByHeader: false,
  allowedDevOrigins: ['localhost', '127.0.0.1'],
  turbopack: {
    root: path.resolve(__dirname),
  },
  // LLM 翻译等长请求需要超过 Next.js rewrite proxy 默认 30s 超时
  experimental: {
    proxyTimeout: 120000,
    optimizePackageImports: ['antd', '@ant-design/icons', 'lucide-react'],
  },
  // 改造方案 11.2：页面搬到新位置的旧路由跳过去；删除的页面（我的母题、内容事件治理、评分看板、
  // 可信线索、Webhook 日志、反馈工作台、发版记录、监控大盘）不再有路由，返回 404。
  // 用 307（permanent: false），避免浏览器永久缓存，后续阶段还会调整。
  async redirects() {
    return [
      { source: '/today-picks', destination: '/?view=picks', permanent: false },
      { source: '/trending', destination: '/hot?tab=list', permanent: false },
      { source: '/trends', destination: '/hot?tab=rising', permanent: false },
      { source: '/my-topics/config', destination: '/hot?tab=terms', permanent: false },
      { source: '/mother-topics/config', destination: '/hot?tab=terms', permanent: false },
      { source: '/admin/mother-topics', destination: '/hot?tab=terms', permanent: false },
      { source: '/topics/:id', destination: '/dossiers', permanent: false },
      { source: '/contents/:id/reader', destination: '/items/:id', permanent: false },
      { source: '/stats', destination: '/sources', permanent: false },
      { source: '/admin', destination: '/sources', permanent: false },
      { source: '/algorithm', destination: '/settings/scoring', permanent: false },
      { source: '/sources/me', destination: '/admin/sources', permanent: false },
      { source: '/settings', destination: '/settings/scoring', permanent: false },
      { source: '/model-eval', destination: '/admin/model-eval', permanent: false },
      { source: '/contents', destination: '/admin/contents', permanent: false },
    ];
  },

  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
          { key: 'Permissions-Policy', value: 'camera=(), geolocation=(), microphone=()' },
        ],
      },
    ];
  },

  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendApiUrl}/api/:path*`,
      },
      // Prometheus 标准采集端点（根路径别名）
      {
        source: '/metrics',
        destination: `${backendApiUrl}/metrics`,
      },
      // 健康检查端点
      {
        source: '/health/:path*',
        destination: `${backendApiUrl}/health/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
