/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['@agent-os/types', '@agent-os/config'],
  experimental: {
    optimizePackageImports: ['lucide-react', '@xyflow/react'],
  },
};

module.exports = nextConfig;
