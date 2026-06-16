import { source } from "@/lib/source";
import { createFromSource } from "fumadocs-core/search/server";

// Static search for `output: "export"`: `staticGET` precomputes the Orama index
// and is emitted as a static JSON file at /api/search during `next build`. The
// client (RootProvider `search.options.type: "static"`) fetches and queries it
// entirely client-side — no server runtime needed on GitHub Pages.
export const revalidate = false;
export const dynamic = "force-static";

export const { staticGET: GET } = createFromSource(source);
