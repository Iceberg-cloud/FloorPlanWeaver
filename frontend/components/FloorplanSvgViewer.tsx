import type { DrawerDraft } from "../lib/types";

export function FloorplanSvgViewer({ drawer }: { drawer: DrawerDraft | null }) {
  const imageSrc =
    drawer?.image_url ??
    (drawer?.image_base64 ? `data:${drawer.image_mime_type};base64,${drawer.image_base64}` : null);

  return (
    <div className="h-full rounded-lg border bg-white p-4">
      <h2 className="text-lg font-semibold">户型平面图</h2>
      {!drawer || !imageSrc ? (
        <p className="mt-3 text-sm text-slate-500">等待绘图结果...</p>
      ) : (
        <div className="mt-3 h-[70vh] overflow-auto rounded border bg-slate-50 p-2">
          <img src={imageSrc} alt="户型平面图" className="w-full rounded object-contain" />
          <div className="mt-2 rounded border bg-white p-2 text-xs text-slate-600">
            <p>模型：{drawer.model}</p>
            <p>尺寸：{drawer.size}</p>
            <p className="mt-1 font-medium text-slate-700">出图提示词</p>
            <p className="mt-1 whitespace-pre-wrap break-words">{drawer.image_prompt}</p>
          </div>
        </div>
      )}
    </div>
  );
}
