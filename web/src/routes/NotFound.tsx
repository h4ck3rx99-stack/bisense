import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/ui";

export default function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-xl">
      <EmptyState title={t("notFound.title")} body={t("notFound.body")} action={<Link to="/">{t("notFound.back")}</Link>} />
    </div>
  );
}
