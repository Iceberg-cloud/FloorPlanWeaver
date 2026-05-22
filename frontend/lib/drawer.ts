import type { DrawerDraft } from "./types";

/** Normalize backend drawer payload for the image viewer. */
export function normalizeDrawer(raw: unknown): DrawerDraft | null {
  if (!raw || typeof raw !== "object") return null;
  const d = raw as Record<string, unknown>;

  const imageBase64 =
    (d.image_base64 as string | undefined) ??
    (d.b64_json as string | undefined) ??
    null;
  const imageUrl = (d.image_url as string | undefined) ?? null;
  const mime =
    (d.image_mime_type as string | undefined) ??
    (imageUrl?.includes(".jpg") ? "image/jpeg" : "image/png");

  if (!imageBase64 && !imageUrl) return null;

  return {
    drawing_state: "IMAGE_READY",
    image_url: imageUrl,
    image_base64: imageBase64,
    image_mime_type: mime,
    image_prompt: String(d.image_prompt ?? ""),
    model: String(d.model ?? ""),
    size: String(d.size ?? "1024x1024"),
    validation: {
      hard_constraints_passed: Boolean(
        (d.validation as { hard_constraints_passed?: boolean } | undefined)
          ?.hard_constraints_passed ?? true,
      ),
      notes: Array.isArray((d.validation as { notes?: string[] } | undefined)?.notes)
        ? ((d.validation as { notes: string[] }).notes)
        : [],
    },
  };
}
