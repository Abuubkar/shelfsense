import Link from "next/link";
import { notFound } from "next/navigation";
import { Evidence } from "@/components/Evidence";
import { ProductArt } from "@/components/ProductArt";
import { ProductTabs } from "@/components/ProductTabs";
import { RankingInfo } from "@/components/RankingInfo";
import { formatMoney } from "@/lib/money";
import { loadProduct, rankingFor, rawAttributesText, similar, spansFor, specs, type Spec } from "@/lib/product";
import { fromParams, toParams } from "@/lib/search-state";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> };

function SpecsTable({ rows }: { rows: Spec[] }) {
  return (
    <table className="specs"><tbody>
      {rows.map((s) => (
        <tr key={s.label}><th>{s.label}</th><td>{s.value}
          <span className="source">{s.source === "seller" ? "from the seller’s data" : <>read from the {s.field?.replace("_", " ")}: “{s.quote}”</>}</span>
        </td></tr>
      ))}
    </tbody></table>
  );
}

export default async function ProductPage({ params, searchParams }: Props) {
  const { id } = await params;
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(await searchParams)) for (const one of [v].flat()) if (one != null) query.append(k, one);
  const search = fromParams(query);

  const product = await loadProduct(id);
  if (!product) notFound();
  const [ranked, alike] = await Promise.all([rankingFor(id, search), similar(product)]);
  const rows = specs(product);
  const color = product.colorBase ?? product.extractedAttributes.find((a) => a.name === "color")?.value;
  const price = formatMoney({ amount_minor: product.price.amountMinor, currency: product.price.currency });
  const description = (product.description ?? "").slice(0, 1500);

  return (
    <>
    <header className="top">
      <Link className="logo" href="/">shelfsense</Link>
      {/* A plain GET form: searching from a product page needs no JavaScript. */}
      <form className="search" role="search" action="/">
        <label htmlFor="q" className="visually-hidden">Search products</label>
        <input id="q" name="q" type="search" defaultValue={search.q} placeholder="Search products" />
        <button type="submit">Search</button>
      </form>
    </header>
    <main className="product">
      <Link className="back" href={`/?${toParams(search)}`}>← Back to results</Link>
      <nav className="crumb" aria-label="Category">
        {(product.category?.fullPath ?? "Not classified yet").split(" > ").join(" › ")}
        {product.category && <span title="How sure the model was"> ({Math.round(product.category.confidence * 100)}%)</span>}
      </nav>
      <div className="hero">
        <figure className="gallery">
          <div className="art-tile"><ProductArt id={product.id} title={product.title} color={color} categoryPath={product.category?.fullPath} className="art" /></div>
          <figcaption>Drawn from the listing; no photo yet.</figcaption>
        </figure>
        <div className="buy">
          <div className="muted">{product.brand}</div>
          <h1><Evidence text={product.title} spans={spansFor(product, "title")} /></h1>
          <div className="price">{price}</div>
          <p className="muted">Sold by {product.supplier}</p>
          <SpecsTable rows={rows.slice(0, 4)} />
        </div>
      </div>
      <ProductTabs tabs={[
        { title: "Description", content: description ? <p><Evidence text={description} spans={spansFor(product, "description")} /></p> : <p className="muted">No description.</p> },
        { title: "Specifications", content: <SpecsTable rows={rows} /> },
        { title: "Evidence", content: (
          <>
            <p className="muted">Highlighted words are what the product’s attributes were read from.</p>
            <p><b>Title</b><br /><Evidence text={product.title} spans={spansFor(product, "title")} /></p>
            <p><b>Description</b><br /><Evidence text={description} spans={spansFor(product, "description")} /></p>
            <p><b>Seller’s columns</b><br /><Evidence text={rawAttributesText(product)} spans={spansFor(product, "raw_attributes")} /></p>
          </>
        ) },
      ]} />
      <section className="section" aria-labelledby="ranking">
        <h2 id="ranking">How the ranking models saw it</h2>
        {ranked ? <RankingInfo {...ranked} hrefFor={(other) => `/products/${other}?${toParams(search)}`} />
          : <p className="muted">Open this product from a search to see how each model ranked it.</p>}
      </section>
      <section className="section" aria-labelledby="similar">
        <h2 id="similar">Similar products</h2>
        {alike.length ? (
          <ul className="similar">{alike.map((i) => (
            <li key={i.id}><Link href={`/products/${i.id}${search.q ? `?${toParams(search)}` : ""}`}><span className="art-tile"><ProductArt id={`s-${i.id}`} title={i.title} color={i.color} categoryPath={i.category_path} className="art" /></span><span>{i.title}</span><span className="price">{formatMoney(i.price)}</span></Link></li>
          ))}</ul>
        ) : <p className="muted">Nothing similar yet.</p>}
      </section>
    </main>
    </>
  );
}
