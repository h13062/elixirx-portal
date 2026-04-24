export interface Machine {
  id: string
  serial_number: string
  product_id: string
  product_name: string | null
  product_sku: string | null
  machine_type: string | null
  batch_number: string
  manufacture_date: string
  status: string
  reserved_by: string | null
  reservation_expires_at: string | null
  registered_by: string
  created_at: string
  updated_at: string
}

export interface ConsumableStock {
  product_id: string
  product_name: string
  product_sku: string | null
  default_price: number
  description: string | null
  quantity: number
  min_threshold: number | null
  alert_enabled: boolean | null
  batch_count: number
  updated_at: string
}

export interface SupplementFlavor {
  id: string
  name: string
  sku: string | null
  description: string | null
  default_price: number | null
  is_active: boolean
  sort_order: number
  total_in_stock: number
  batch_count: number
}

export interface ConsumableBatch {
  id: string
  product_id: string
  product_name: string | null
  product_sku: string | null
  flavor_id: string | null
  flavor_name: string | null
  flavor_sku: string | null
  batch_number: string
  quantity_manufactured: number
  quantity: number
  quantity_shipped: number
  manufacture_date: string
  expiry_date: string | null
  shipped_date: string | null
  shipped_to: string | null
  status: string
  notes: string | null
  added_by: string | null
  created_at: string
  updated_at: string
}

export interface Product {
  id: string
  name: string
  category: string
  default_price: number
  sku: string | null
  description: string | null
  is_serialized: boolean
  is_active: boolean
}

export type StatusFilter =
  | 'all'
  | 'available'
  | 'reserved'
  | 'ordered'
  | 'sold'
  | 'delivered'
  | 'returned'

export type TypeFilter = 'all' | 'RX' | 'RO'

export type StatusCounts = Record<StatusFilter, number>
