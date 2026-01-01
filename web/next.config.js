/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000',
  },
  devIndicators: {
    buildActivity: false,
  },
  // 禁用 IPv6，使用 IPv4
  experimental: {
    // disableIPv6: true,
  },
  // 设置默认主机和端口
  // 注意：这些选项需要在命令行中传递，而不是在这里
}

module.exports = nextConfig
