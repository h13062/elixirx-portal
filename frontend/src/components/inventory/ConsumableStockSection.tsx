import './ConsumableStockSection.css'
import type { ConsumableStock } from './types'

interface Props {
  stock: ConsumableStock[]
  loading: boolean
}

type Accent = 'accent-blue' | 'accent-cyan' | 'accent-violet'

const ACCENT_FALLBACK: Accent[] = ['accent-blue', 'accent-cyan', 'accent-violet']

function resolveAccent(sku: string | null, index: number): Accent {
  if (sku) {
    const s = sku.toUpperCase()
    if (s.startsWith('RO'))   return 'accent-blue'
    if (s.startsWith('AC'))   return 'accent-cyan'
    if (s.startsWith('SUPP')) return 'accent-violet'
  }
  return ACCENT_FALLBACK[index % 3] ?? 'accent-blue'
}

function SkeletonCards() {
  return (
    <>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="stock-card-skeleton">
          <div className="skeleton-line h-sm w-short" />
          <div className="skeleton-line h-lg w-mid" />
          <div className="skeleton-line h-sm w-long" />
        </div>
      ))}
    </>
  )
}

export default function ConsumableStockSection({ stock, loading }: Props) {
  return (
    <section className="stock-section">
      <h2 className="stock-section-title">Consumable Stock</h2>

      <div className="stock-cards">
        {loading ? (
          <SkeletonCards />
        ) : stock.length === 0 ? (
          <p className="stock-empty">No consumable stock data available.</p>
        ) : (
          stock.map((item, i) => (
            <div key={item.product_id} className={`stock-card ${resolveAccent(item.product_sku, i)}`}>
              <p className="stock-card-name">{item.product_name}</p>
              <p className="stock-card-qty">{item.quantity}</p>
              <p className="stock-card-meta">in stock · ${item.default_price.toFixed(2)}</p>
              <button className="stock-card-update-btn">Update Stock</button>
            </div>
          ))
        )}
      </div>
    </section>
  )
}
