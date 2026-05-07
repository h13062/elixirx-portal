/**
 * Shared file-download helpers.
 *
 * All downloads route through `apiGetBlob`, which sits on top of `fetchWithAuth`,
 * so token refresh-on-401 happens transparently.
 */

import { apiGetBlob } from './api'

/**
 * Download a warranty certificate PDF for the given machine.
 *
 * @param machineIdentifier  UUID or serial number — backend resolves either.
 * @param serialNumber       Used in the saved filename for human-friendliness.
 * @param token              Bearer token (legacy parameter; ignored by the
 *                           api.ts helpers that read it from supabase session).
 * @returns true on success, false on failure (caller may show a toast).
 */
export async function downloadWarrantyCertificate(
  machineIdentifier: string,
  serialNumber: string | null | undefined,
  token?: string,
): Promise<boolean> {
  try {
    const blob = await apiGetBlob(
      `/api/warranty/certificate/${machineIdentifier}`,
      token,
    )
    const filename = `ElixirX_Warranty_${serialNumber || machineIdentifier}.pdf`
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    return true
  } catch (err) {
    console.error('Certificate download failed:', err)
    return false
  }
}
