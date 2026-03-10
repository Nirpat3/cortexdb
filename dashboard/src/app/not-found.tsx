import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4">
      <div className="glass-heavy rounded-2xl p-8 w-full max-w-md text-center">
        <div className="text-6xl font-bold text-white/10 mb-4">404</div>

        <h1 className="text-xl font-bold text-white mb-2">Page Not Found</h1>
        <p className="text-sm text-white/50 mb-8">
          The page you are looking for does not exist or has been moved.
        </p>

        <Link
          href="/"
          className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-cortex-blue/20 text-cortex-blue hover:bg-cortex-blue/30 transition text-sm font-medium"
        >
          Back to Home
        </Link>
      </div>
    </div>
  );
}
