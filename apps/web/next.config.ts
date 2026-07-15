import type { NextConfig } from "next";

const apiUrl = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const staticExport = process.env.ESA_STATIC_EXPORT === "true";

const nextConfig: NextConfig = {
  output: staticExport ? "export" : "standalone",
  trailingSlash: staticExport,
  images: { unoptimized: staticExport },
  poweredByHeader: false,
  compress: true,
  ...(staticExport
    ? {}
    : {
        async rewrites() {
          return [{ source: "/backend/:path*", destination: `${apiUrl}/:path*` }];
        },
        async headers() {
          return [{
            source: "/(.*)",
            headers: [
              { key: "X-Content-Type-Options", value: "nosniff" },
              { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
              { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
              { key: "X-Frame-Options", value: "DENY" },
            ],
          }];
        },
      }),
};

export default nextConfig;
