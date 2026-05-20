/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: false,
    devIndicators: false,
    output: 'standalone',
    typescript: {
        ignoreBuildErrors: true,
    },
    eslint: {
        ignoreDuringBuilds: true,
    },
}

module.exports = nextConfig
