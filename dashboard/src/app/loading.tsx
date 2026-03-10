export default function RootLoading() {
  return (
    <div className="min-h-screen bg-black flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 rounded-full border-2 border-white/10 border-t-cortex-blue animate-spin" />
        <p className="text-sm text-white/30">Loading CortexDB...</p>
      </div>
    </div>
  );
}
