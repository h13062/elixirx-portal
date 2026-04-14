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
  quantity: number
  updated_at: string
}

export interface Product {
  id: string
  name: string
  category: string
  default_price: number
  sku: string | null
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
