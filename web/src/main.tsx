import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/noto-sans-devanagari/400.css";
import "@fontsource/noto-sans-devanagari/600.css";
import "@fontsource/noto-sans-kannada/400.css";
import "@fontsource/noto-sans-kannada/600.css";
import "./styles/index.css";
import "./i18n";
import { Layout } from "./components/Layout";
import { ToastProvider } from "./components/Toast";
import { Skeleton } from "./components/ui";
import Home from "./routes/Home";
import Ask from "./routes/Ask";

// Route-level code splitting: heavier, less frequent screens load on demand.
const Library = lazy(() => import("./routes/Library"));
const Explorer = lazy(() => import("./routes/Explorer"));
const Checklist = lazy(() => import("./routes/Checklist"));
const Compare = lazy(() => import("./routes/Compare"));
const About = lazy(() => import("./routes/About"));
const NotFound = lazy(() => import("./routes/NotFound"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 60_000 } },
});

function PageFallback() {
  return (
    <div className="space-y-3" aria-busy="true">
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Layout>
            <Suspense fallback={<PageFallback />}>
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/ask" element={<Ask />} />
                <Route path="/standards" element={<Library />} />
                <Route path="/standards/:slug" element={<Explorer />} />
                <Route path="/standards/:slug/checklist" element={<Checklist />} />
                <Route path="/compare" element={<Compare />} />
                <Route path="/about" element={<About />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </Suspense>
          </Layout>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
