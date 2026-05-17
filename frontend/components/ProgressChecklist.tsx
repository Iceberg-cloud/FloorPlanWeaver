export function ProgressChecklist({
  collected,
  missing
}: {
  collected: string[];
  missing: string[];
}) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <h3 className="text-sm font-semibold text-slate-900">信息收集进度</h3>
      <div className="mt-2">
        <p className="text-xs text-slate-500">已收集字段</p>
        <div className="mt-1 flex flex-wrap gap-1">
          {collected.map((item) => (
            <span key={item} className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">
              {item}
            </span>
          ))}
        </div>
      </div>
      <div className="mt-3">
        <p className="text-xs text-slate-500">缺失字段</p>
        <div className="mt-1 flex flex-wrap gap-1">
          {missing.map((item) => (
            <span key={item} className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
              {item}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
