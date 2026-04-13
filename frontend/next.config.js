/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Produce .next/standalone — a self-contained Node server with minimal deps.
  // Required by the Docker image to run `node server.js`.
  output: "standalone",
};

module.exports = nextConfig;
