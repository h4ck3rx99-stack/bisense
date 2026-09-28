// Guided path for people who don't know what to search for.
// Step 1: "What are you looking for?" (icon options). Step 2: a product description and/or a category taken
// from the categories actually present in the library. Results are either the real standards in that
// category (from /api/standards) or a question sent through the normal answer pipeline (/ask).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Award, BadgeCheck, Factory, FlaskConical, MessageCircle, Package, ShieldCheck, type LucideIcon } from "lucide-react";
import { api } from "../api/client";
import { useLibrary } from "../lib/hooks";
import { shortTitle } from "../lib/format";
import { Badge, ErrorState, Skeleton, SyntheticBadge } from "../components/ui";

type Goal = "product" | "industry" | "testing" | "safety" | "quality" | "certification" | "other";

const GOALS: { k: Goal; icon: LucideIcon }[] = [
  { k: "product", icon: Package },
  { k: "industry", icon: Factory },
  { k: "testing", icon: FlaskConical },
  { k: "safety", icon: ShieldCheck },
  { k: "quality", icon: BadgeCheck },
  { k: "certification", icon: Award },
  { k: "other", icon: MessageCircle },
];

const CATEGORY_LIMIT = 12;

function CategoryResults({ category }: { category: string }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["guide-cat", category], queryFn: () => api.standards({ category, page_size: 12 }) });
  if (q.isError) return <ErrorState messageKey="error.network" onRetry={() => q.refetch()} />;
  if (!q.data)
    return (
      <div className="space-y-2" aria-busy="true">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  return (
    <section aria-labelledby="guide-results" className="space-y-2">
      <h2 id="guide-results" className="text-[15px] font-semibold">
        {t("guide.resultsTitle", { category, count: q.data.total })}
      </h2>
      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
        {q.data.items.map((s) => (
          <li key={s.slug} className="flex items-start gap-3 p-3">
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-medium leading-snug">{shortTitle(s.title, 110)}</div>
              <div className="mt-0.5 flex flex-wrap items-center gap-2">
                {s.number && <span className="mono text-[13px] text-ink-2">{s.number}</span>}
                {s.synthetic && <SyntheticBadge compact />}
                {s.catalogue_only && <Badge tone="calm">{t("standard.catalogueOnlyShort")}</Badge>}
              </div>
            </div>
            <Link to={`/standards/${s.slug}`} className="inline-flex h-9 shrink-0 items-center gap-1 rounded-md border border-line-strong px-3 text-[13px] font-medium text-ink no-underline hover:border-accent">
              {t("answer.open")}
              <ArrowRight size={14} aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
      {q.data.total > q.data.items.length && (
        <Link to={`/standards?category=${encodeURIComponent(category)}`} className="inline-block text-[13px]">
          {t("guide.seeAll", { count: q.data.total })}
        </Link>
      )}
    </section>
  );
}

export default function Guide() {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const library = useLibrary();
  const [params] = useSearchParams();
  const initialGoal = params.get("goal");
  const [goal, setGoal] = useState<Goal | null>(GOALS.some((g) => g.k === initialGoal && g.k !== "other") ? (initialGoal as Goal) : null);
  const [product, setProduct] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [allCats, setAllCats] = useState(false);

  const cats = [...(library.data?.categories ?? [])].sort((a, b) => b.count - a.count);
  const shownCats = allCats ? cats : cats.slice(0, CATEGORY_LIMIT);

  const ask = (q: string) => nav(`/ask?q=${encodeURIComponent(q)}&lang=${i18n.language}`);
  const submitProduct = (e: React.FormEvent) => {
    e.preventDefault();
    const p = product.trim();
    if (!p || !goal) return;
    ask(t(`guide.query.${goal === "industry" ? "product" : goal}`, { product: p }));
  };

  const pick = (g: Goal) => {
    if (g === "other") {
      nav("/", { state: { focusSearch: true } });
      return;
    }
    setGoal(g);
    setCategory(null);
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {!goal ? (
        <section aria-labelledby="guide-title" className="space-y-4">
          <div>
            <h1 id="guide-title" className="text-2xl font-semibold">{t("guide.title")}</h1>
            <p className="mt-1 text-ink-2">{t("guide.subtitle")}</p>
          </div>
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {GOALS.map(({ k, icon: Icon }) => (
              <li key={k}>
                <button
                  type="button"
                  onClick={() => pick(k)}
                  className="card flex h-full min-h-[88px] w-full flex-col items-start gap-2 p-3 text-left hover:border-accent focus-visible:border-accent"
                >
                  <Icon size={22} className="text-accent" aria-hidden />
                  <span className="text-[15px] font-medium leading-snug">{t(`guide.goal.${k}`)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <section aria-labelledby="guide-step2" className="space-y-5">
          <button type="button" onClick={() => setGoal(null)} className="inline-flex min-h-9 items-center gap-1 text-[13px] font-medium text-ink-2 hover:text-accent">
            <ArrowLeft size={14} aria-hidden />
            {t("guide.back")}
          </button>
          <h1 id="guide-step2" className="text-2xl font-semibold">{t(`guide.step2.${goal}`)}</h1>

          {goal !== "industry" && (
            <form onSubmit={submitProduct} className="space-y-2">
              <label htmlFor="guide-product" className="block text-[14px] font-medium">
                {t("guide.productLabel")}
              </label>
              <div className="flex gap-2">
                <input
                  id="guide-product"
                  value={product}
                  onChange={(e) => setProduct(e.target.value)}
                  maxLength={120}
                  placeholder={t("guide.productPlaceholder")}
                  className="h-11 min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-3 text-[15px]"
                  autoFocus
                />
                <button type="submit" disabled={!product.trim()} className="inline-flex h-11 items-center gap-1 rounded-md bg-accent px-4 font-medium text-white disabled:opacity-50">
                  {t("guide.find")}
                  <ArrowRight size={16} aria-hidden />
                </button>
              </div>
            </form>
          )}

          <div className="space-y-2">
            <p className="text-[14px] font-medium">{goal === "industry" ? t("guide.pickIndustry") : t("guide.orPickCategory")}</p>
            {!library.data ? (
              <Skeleton className="h-10 w-full" />
            ) : cats.length === 0 ? (
              <p className="text-[13px] text-ink-3">{t("guide.noCategories")}</p>
            ) : (
              <div className="flex flex-wrap gap-2" role="group" aria-label={t("guide.categories")}>
                {shownCats.map((c) => (
                  <button
                    key={c.category}
                    type="button"
                    aria-pressed={category === c.category}
                    onClick={() => setCategory(c.category)}
                    className={`min-h-10 rounded-md border px-3 py-1 text-left text-[13px] ${category === c.category ? "border-accent bg-accent-soft text-accent-strong" : "border-line bg-surface text-ink-2 hover:border-accent"}`}
                  >
                    {c.category} <span className="text-ink-3">({c.count})</span>
                  </button>
                ))}
                {cats.length > CATEGORY_LIMIT && (
                  <button type="button" onClick={() => setAllCats((v) => !v)} className="min-h-10 px-2 text-[13px] font-medium text-accent hover:underline">
                    {allCats ? t("answer.fewerPoints") : t("guide.moreCategories", { count: cats.length - CATEGORY_LIMIT })}
                  </button>
                )}
              </div>
            )}
          </div>

          {category && <CategoryResults category={category} />}
        </section>
      )}
      <p className="text-[13px] text-ink-3">
        {t("guide.switch")} <Link to="/">{t("guide.switchLink")}</Link>
      </p>
    </div>
  );
}
