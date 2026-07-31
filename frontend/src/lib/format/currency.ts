/** Format a number as MXN with 0 decimal places (e.g. $1,234). */
export function formatMXN0(n: number): string {
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 0,
  }).format(n);
}
