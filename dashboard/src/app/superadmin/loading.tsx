export default function SuperAdminLoading() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 rounded-full border-2 border-white/10 border-t-cortex-blue animate-spin" />
        <p className="text-sm text-white/30">Loading...</p>
      </div>
    </div>
  );
}
