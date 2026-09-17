import { source } from "@/lib/source";
import { DocsPage, DocsBody, DocsTitle, DocsDescription } from "fumadocs-ui/layouts/docs/page";
import { getMDXComponents } from "../../../../mdx-components";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import ContributorWall, { CONTRIBUTING_URL, contributorCounts } from "@/components/ContributorWall";

interface Props {
  params: Promise<{ slug?: string[] }>;
}

export async function generateStaticParams() {
  return source.generateParams();
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const page = source.getPage(slug);
  if (!page) return {};
  return {
    title: page.data.title,
    description: page.data.description,
  };
}

export default async function Page({ params }: Props) {
  const { slug } = await params;
  const page = source.getPage(slug);
  if (!page) notFound();

  const MDX = page.data.body;
  const isHome = !slug || slug.length === 0;

  return (
    <DocsPage toc={page.data.toc}>
      {isHome ? (
        // Docs home: contributor wall beside the title, like Astro's docs landing.
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <DocsTitle>{page.data.title}</DocsTitle>
            <DocsDescription>{page.data.description}</DocsDescription>
          </div>
          <figure className="shrink-0 xl:-mt-2">
            <ContributorWall columns={8} size={30} className="xl:ml-auto" />
            <figcaption className="mt-3 max-w-[300px] text-[12.5px] leading-relaxed text-[var(--tt-fg-muted)] xl:ml-auto xl:text-right">
              Built by {contributorCounts.total} people who wrote code, reported bugs, or shaped features.{" "}
              <a href={CONTRIBUTING_URL} target="_blank" rel="noopener noreferrer"
                className="text-[var(--tt-brand)] underline underline-offset-2">
                Join us
              </a>
            </figcaption>
          </figure>
        </div>
      ) : (
        <>
          <DocsTitle>{page.data.title}</DocsTitle>
          <DocsDescription>{page.data.description}</DocsDescription>
        </>
      )}
      <DocsBody>
        <MDX components={getMDXComponents()} />
      </DocsBody>
    </DocsPage>
  );
}
