// Page preview dialog: the original PDF page rendered by the server with the quote highlighted.
import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import type { Citation } from "../api/types";
import { pageImageUrl } from "../api/client";
import { sourceLabel } from "../lib/format";
import { Skeleton, SyntheticBadge } from "./ui";

export function PagePreviewDialog({ c, quote, onClose }: { c: Pick<Citation, "slug" | "page_start" | "standard_number" | "standard_title" | "clause_number" | "synthetic">; quote?: string | null; onClose: () => void }) {
  const { t } = useTranslation();
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const firstLine = (quote ?? "").split(/\n|\|/).map((s) => s.trim()).find((s) => s.length > 8) ?? "";
  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[rgb(20_20_30/0.45)]" />
        <Dialog.Content className="fixed inset-2 z-50 mx-auto flex max-w-3xl flex-col overflow-hidden rounded-lg bg-surface shadow-[var(--shadow-pop)] sm:inset-6">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <Dialog.Title className="mono truncate text-[14px] font-semibold">
                {sourceLabel(c)} · {t("evidence.page", { n: c.page_start })}
              </Dialog.Title>
              <Dialog.Description className="text-xs text-ink-3">{t("evidence.previewNote")}</Dialog.Description>
            </div>
            <div className="flex items-center gap-2">
              {c.synthetic && <SyntheticBadge compact />}
              <Dialog.Close className="rounded-md p-2 hover:bg-surface-2" aria-label={t("action.close")}>
                <X size={18} aria-hidden />
              </Dialog.Close>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto bg-surface-2 p-3">
            {!loaded && !failed && <Skeleton className="mx-auto aspect-[1/1.41] w-full max-w-2xl" />}
            {failed ? (
              <p className="p-6 text-ink-2">{t("evidence.previewUnavailable")}</p>
            ) : (
              <img
                src={pageImageUrl(c.slug, c.page_start, firstLine)}
                alt={t("evidence.pageAlt", { source: sourceLabel(c), n: c.page_start })}
                className={`mx-auto w-full max-w-2xl rounded border border-line bg-white ${loaded ? "" : "hidden"}`}
                onLoad={() => setLoaded(true)}
                onError={() => setFailed(true)}
              />
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
