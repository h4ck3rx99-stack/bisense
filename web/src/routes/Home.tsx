// Home: one message, one input, a few doors. In seconds a first-time visitor should understand:
// "Find the BIS standards related to what you make, sell, buy or study, explained simply, with official sources."
// No hero, no feature list. Example chips are questions verified against the data mode that is loaded.
import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, BookOpen, Columns2, ExternalLink, FlaskConical, MessageSquareText, Package, ShieldCheck, type LucideIcon } from "lucide-react";
import { SearchBar, type SearchBarHandle } from "../components/SearchBar";
import { Skeleton } from "../components/ui";
import { useHealth, useLibrary } from "../lib/hooks";
import { recentStandards } from "../lib/storage";
import { shortTitle } from "../lib/format";

// Official data: each example is in docs/demo_questions.yaml and checked by `npm run eval` / `npm run warm`.
const OFFICIAL_EXAMPLES: { q: string; lang: string }[] = [
  { q: "Is BIS certification compulsory for two-wheeler helmets?", lang: "en" },
  { q: "How can I check that gold jewellery is hallmarked?", lang: "en" },
  { q: "Where can I get my product tested for BIS certification?", lang: "en" },
  { q: "पैकेज्ड पेयजल के लिए कौन-से BIS मानक लागू होते हैं?", lang: "hi" },
  { q: "ಚಿನ್ನದ ಆಭರಣಕ್ಕೆ ಹಾಲ್‌ಮಾರ್ಕ್ ಹೇಗೆ ಪರಿಶೀಲಿಸುವುದು?", lang: "kn" },
];
// Sample mode (DATASET=sample): questions the sample pack can answer (tests/test_rag_mechanism.py, e2e).
const SAMPLE_EXAMPLES: { q: string; lang: string }[] = [
  { q: "What must be marked on a two-wheeler helmet?", lang: "en" },
  { q: "What are the requirements for packaged drinking water?", lang: "en" },
  { q: "How are bundles of steel bars tied?", lang: "en" },
];

const DOORS: { k: string; to: string; icon: LucideIcon }[] = [
  { k: "product", to: "/guide?goal=product", icon: Package },
  { k: "ask", to: "#ask", icon: MessageSquareText },
  { k: "understand", to: "/standards", icon: BookOpen },
  { k: "check", to: "/guide?goal=certification", icon: ShieldCheck },
  { k: "compare", to: "/compare", icon: Columns2 },
];

export default function Home() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const location = useLocation();
  const health = useHealth();
  const library = useLibrary();
  const search = useRef<SearchBarHandle>(null);
  const recent = useMemo(() => recentStandards(), []);
  const go = (q: string) => nav(`/ask?q=${encodeURIComponent(q)}&lang=${i18n.language}`);
  const sample = health.data?.dataset_mode === "sample";
  const examples = sample ? SAMPLE_EXAMPLES : OFFICIAL_EXAMPLES;

  // "Something else" in the guided path lands here with the input focused.
  useEffect(() => {
    if ((location.state as { focusSearch?: boolean } | null)?.focusSearch) search.current?.focus();
  }, [location.state]);

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <section aria-labelledby="home-title" className="space-y-4 pt-2 sm:pt-6">
        <h1 id="home-title" className="text-[26px] font-semibold leading-tight sm:text-[32px]">
          {t("home.title")}
        </h1>
        <p className="text-[16px] text-ink-2">{t("home.subtitle")}</p>
        <SearchBar ref={search} onSubmit={go} autoFocus placeholder={t("home.placeholder")} />
        <div className="flex flex-wrap gap-2" aria-label={t("home.examples")}>
          {examples.map((e) => (
            <button
              key={e.q}
              type="button"
              lang={e.lang}
              onClick={() => nav(`/ask?q=${encodeURIComponent(e.q)}&lang=${e.lang}`)}
              className="min-h-10 rounded-md border border-line bg-surface px-3 py-1 text-left text-[13px] text-ink-2 hover:border-accent hover:text-accent-strong"
            >
              {e.q}
            </button>
          ))}
        </div>
        {sample && (
          <div className="flex items-start gap-3 rounded-lg border border-dashed border-synth-line bg-synth-bg p-3 text-[14px] text-synth-ink" role="note">
            <FlaskConical size={18} className="mt-0.5 shrink-0" aria-hidden />
            <p>
              {t("home.sampleBanner")} <Link to="/about#data" className="font-medium underline">{t("home.demoBannerLink")}</Link>
            </p>
          </div>
        )}
      </section>

      <nav aria-label={t("home.doorsLabel")}>
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {DOORS.map(({ k, to, icon: Icon }) => (
            <li key={k} className={k === "compare" ? "col-span-2 sm:col-span-1" : ""}>
              {to === "#ask" ? (
                <button type="button" onClick={() => search.current?.focus()} className="card flex h-full min-h-[84px] w-full flex-col items-start gap-2 p-3 text-left hover:border-accent">
                  <Icon size={20} className="text-accent" aria-hidden />
                  <span className="text-[14px] font-medium leading-snug">{t(`home.door.${k}`)}</span>
                </button>
              ) : (
                <Link to={to} className="card flex h-full min-h-[84px] flex-col items-start gap-2 p-3 text-ink no-underline hover:border-accent">
                  <Icon size={20} className="text-accent" aria-hidden />
                  <span className="text-[14px] font-medium leading-snug">{t(`home.door.${k}`)}</span>
                </Link>
              )}
            </li>
          ))}
        </ul>
      </nav>

      <section aria-label={t("home.aboutLabel")} className="space-y-2 border-t border-line pt-4 text-[14px] text-ink-2">
        <p>
          <span className="font-semibold text-ink">{t("home.whatIsBis")}</span> {t("home.whatIsBisBody")}{" "}
          <a href="https://www.bis.gov.in/" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5">
            {t("home.learnMore")}
            <ExternalLink size={12} aria-hidden />
          </a>
        </p>
        {!library.data ? <Skeleton className="h-4 w-2/3" /> : <p className="text-[13px] text-ink-3">{t("home.coverage", { line: library.data.coverage })}</p>}
      </section>

      {recent.length > 0 && (
        <section aria-labelledby="recent-title">
          <h2 id="recent-title" className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">{t("home.recent")}</h2>
          <ul className="flex flex-wrap gap-2">
            {recent.slice(0, 4).map((r) => (
              <li key={r.slug}>
                <Link to={`/standards/${r.slug}`} className="card flex max-w-[18rem] items-center gap-2 px-3 py-2 text-ink no-underline hover:border-accent">
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-medium">{shortTitle(r.title, 60)}</span>
                    {r.number && <span className="mono block text-xs text-ink-3">{r.number}</span>}
                  </span>
                  <ArrowRight size={14} className="shrink-0 text-ink-3" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
