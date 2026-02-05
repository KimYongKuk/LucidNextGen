/** @type {import('next').NextConfig} */
const nextConfig = {
    devIndicators: false,
    // experimental: {
    //   serverActions: {
    //     bodySizeLimit: '10mb',
    //   },
    // },
    images: {
        remotePatterns: [
            {
                protocol: 'https',
                hostname: '**',
            },
            {
                protocol: 'http',
                hostname: '**',
            },
        ],
    },
    async rewrites() {
        // 환경 변수에서 백엔드 URL 가져오기 (기본값: localhost:8000)
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

        return [
            // 백엔드 API 프록시 (클라이언트에서 직접 접근 가능하도록)
            {
                source: '/api/v1/:path*',
                destination: `${backendUrl}/api/v1/:path*`,
            },
            {
                source: '/api/:path*',
                destination: `${backendUrl}/api/:path*`,
            },
            {
                source: '/health',
                destination: `${backendUrl}/health`,
            },
        ];
    },
};

module.exports = nextConfig;
