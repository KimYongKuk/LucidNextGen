/** @type {import('next').NextConfig} */
const nextConfig = {
    // experimental: {
    //   serverActions: {
    //     bodySizeLimit: '10mb',
    //   },
    // },
    async rewrites() {
        return [
            {
                source: '/api/:path*',
                destination: 'http://localhost:8000/api/:path*',
            },
            {
                source: '/health',
                destination: 'http://localhost:8000/health',
            },
        ];
    },
};

module.exports = nextConfig;
