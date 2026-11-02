import { Suspense } from "react";
import { SearchPage } from "@/components/SearchPage";

export default function Home() {
  // useSearchParams needs a Suspense boundary when the page is prerendered.
  return <Suspense><SearchPage /></Suspense>;
}
