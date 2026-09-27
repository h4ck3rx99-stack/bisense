// Search-first home. Compact header (not a hero), verified example queries, real library counts.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, BookMarked, Columns2, FileSearch, FlaskConical, ListChecks, Quote, ShieldCheck, Split } from "lucide-react";
import { SearchBar } from "../components/SearchBar";
import { SectionTitle, Skeleton } from "../components/ui";
import { useHealth, useLibrary } from "../lib/hooks";
import { recentStandards } from "../lib/storage";
import { shortTitle } from "../lib/format";

// Example queries: each one is part of docs/demo_questions.yaml and verified by `npm run warm`/eval.
const EXAMPLES: { q: string; lang: string; wide?: boolean }[] = [
  { q: "What BIS standards apply to packaged drinking water?", lang: "en" },
  { q: "Is BIS certification compulsory for two-wheeler helmets?", lang: "en" },
  { q: "How can I check that gold jewellery is hallmarked?", lang: "en", wide: true },
  { q: "Where can I get my product tested for BIS certification?", lang: "en", wide: true },
  { q: "पैकेज्ड पेयजल के लिए कौन-से BIS मानक लागू होते हैं?", lang: "hi" },
  { q: "ಚಿನ್ನದ ಆಭರಣಕ್ಕೆ ಹಾಲ್‌ಮಾರ್ಕ್ ಹೇಗೆ ಪರಿಶೀಲಿಸುವುದು?", lang: "kn" },
];

export default function Home() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const health = useHealth();
  const library = useLibrary();
  const recent = useMemo(() => recentStandards(), []);
  const go = (q: string) => nav(`/ask?q=${encodeURIComponent(q)}&lang=${i18n.language}`);
  const counts = health.data?.counts;
  const guidanceCats = (library.data?.categories ?? []).filter((c) => c.kind === "guidance" || c.kind === "order");
  const stdCats = (library.data?.categories ?? []).filter((c) => c.kind === "standard");
  const demo = health.data?.dataset_mode === "demo";

  const libraryPanel = (
    <section aria-labelledby="lib-title">
      <SectionTitle id="lib-title" right={<Link to="/standards" className="text-[13px]">{t("home.browseAll")}</Link>}>
        {t("home.library")}
      </SectionTitle>
      <div className="card divide-y divide-line">
        {!counts ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-5 w-1/2" />
            <Skeleton className="h-5 w-3/4" />
          </div>
        ) : (
          <>
            <Link to="/standards?kind=standard" className="flex items-center justify-between gap-3 p-3 text-ink no-underline hover:bg-surface-2">
              <span className="min-w-0">
                <span className="block text-[14px] font-medium">{t("home.fullText")}</span>
                <span className="block truncate text-xs text-ink-3">{stdCats.map((c) => c.category).join(" · ") || t("home.none")}</span>
              </span>
              <span className="mono text-xl font-semibold">{counts.standards_full_text}</span>
            </Link>
            <Link to="/standards?kind=guidance,order" className="flex items-center justify-between gap-3 p-3 text-ink no-underline hover:bg-surface-2">
              <span className="min-w-0">
                <span className="block text-[14px] font-medium">{t("home.guidance")}</span>
                <span className="block text-xs text-ink-3">{guidanceCats.slice(0, 5).map((c) => c.category).join(" · ")}</span>
              </span>
              <span className="mono text-xl font-semibold">{counts.guidance}</span>
            </Link>
            <Link to="/standards?kind=catalogue" className="flex items-center justify-between gap-3 p-3 text-ink no-underline hover:bg-surface-2">
              <span className="min-w-0">
                <span className="block text-[14px] font-medium">{t("home.catalogue")}</span>
                <span className="block text-xs text-ink-3">{t("home.catalogueNote")}</span>
              </span>
              <span className="mono text-xl font-semibold">{counts.catalogue}</span>
            </Link>
          </>
        )}
      </div>
    </section>
  );

  const workflows = (
    <section aria-labelledby="flow-title">
      <SectionTitle id="flow-title">{t("home.workflows")}</SectionTitle>
      <div className="card divide-y divide-line">
        {[
          { to: "/ask?q=" + encodeURIComponent(t("home.flowAskQuery")), icon: FileSearch, k: "ask" },
          { to: "/standards/demo-101-2026?tab=requirements", icon: ListChecks, k: "requirements" },
          { to: "/compare?a=demo-101-2026&b=demo-102-2026", icon: Columns2, k: "compare" },
        ].map(({ to, icon: Icon, k }) => (
          <Link key={k} to={to} className="group flex items-start gap-3 p-3 text-ink no-underline hover:bg-surface-2">
            <Icon size={17} className="mt-0.5 shrink-0 text-accent" aria-hidden />
            <span className="flex-1">
              <span className="block text-[14px] font-medium">{t(`home.flow.${k}.title`)}</span>
              <span className="block text-[13px] text-ink-2">{t(`home.flow.${k}.body`)}</span>
            </span>
            <ArrowRight size={16} className="mt-1 text-ink-3 group-hover:text-accent" aria-hidden />
          </Link>
        ))}
      </div>
    </section>
  );

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section aria-labelledby="home-title" className="min-w-0">
          <h1 id="home-title" className="text-[26px] font-semibold leading-tight sm:text-3xl">
            {t("home.title")}
          </h1>
          <p className="mt-2 max-w-2xl text-[16px] text-ink-2">{t("home.subtitle")}</p>
          <div className="mt-5">
            <SearchBar onSubmit={go} autoFocus />
          </div>
          <div className="mt-2 flex flex-wrap gap-2" aria-label={t("home.examples")}>
            {EXAMPLES.map((e) => (
              <button
                key={e.q}
                type="button"
                lang={e.lang}
                onClick={() => nav(`/ask?q=${encodeURIComponent(e.q)}&lang=${e.lang}`)}
                className={`min-h-9 rounded-md border border-line bg-surface px-3 py-1 text-left text-[13px] text-ink-2 hover:border-accent hover:text-accent-strong ${e.wide ? "hidden sm:block" : ""}`}
              >
                {e.q}
              </button>
            ))}
          </div>
          {demo && (
            <div className="mt-5 flex items-start gap-3 rounded-lg border border-dashed border-synth-line bg-synth-bg p-3.5 text-[14px] text-synth-ink">
              <FlaskConical size={18} className="mt-0.5 shrink-0" aria-hidden />
              <p>
                {t("home.demoBanner", { std: counts?.standards_full_text ?? 0, guide: counts?.guidance ?? 0 })}{" "}
                <Link to="/about#data">{t("home.demoBannerLink")}</Link>
              </p>
            </div>
          )}
        </section>
        <div className="space-y-5 lg:pt-1">
          {libraryPanel}
          {workflows}
        </div>
      </div>

      <section aria-labelledby="why-title" className="grid gap-3 border-y border-line py-4 sm:grid-cols-3">
        <h2 id="why-title" className="sr-only">{t("why.title")}</h2>
        {[
          { icon: Quote, k: "why.cite" },
          { icon: ShieldCheck, k: "why.refuse" },
          { icon: Split, k: "why.separate" },
        ].map(({ icon: Icon, k }) => (
          <div key={k} className="flex gap-3">
            <Icon size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
            <div>
              <div className="text-[14px] font-semibold">{t(`${k}.title`)}</div>
              <div className="text-[13px] text-ink-2">{t(`${k}.body`)}</div>
            </div>
          </div>
        ))}
      </section>

      <section aria-labelledby="recent-title">
        <SectionTitle id="recent-title">{t("home.recent")}</SectionTitle>
        {recent.length === 0 ? (
          <p className="flex items-start gap-2 text-[13px] text-ink-3">
            <BookMarked size={16} className="mt-0.5 shrink-0" aria-hidden />
            {t("home.recentEmpty")}
          </p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {recent.slice(0, 6).map((r) => (
              <li key={r.slug}>
                <Link to={`/standards/${r.slug}`} className="card block max-w-[18rem] px-3 py-2 no-underline hover:border-accent">
                  <span className="mono block text-[13px] font-semibold text-ink">{r.number ?? t(`kind.${r.kind}`)}</span>
                  <span className="block truncate text-[13px] text-ink-2">{shortTitle(r.title, 60)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
