const STYLE_ID = "walix-tenant-brand";

export function applyBrandPrimary(value?: string | null) {
  removeBrandPrimary();
  if (!value) return;
  const hsl = normalize(value);
  if (!hsl) return;
  const fg = derivedForeground(hsl);
  const css = `:root{--primary:${hsl};--primary-foreground:${fg};--ring:${hsl};}`;
  const tag = document.createElement("style");
  tag.id = STYLE_ID;
  tag.textContent = css;
  document.head.appendChild(tag);
}

export function removeBrandPrimary() {
  document.getElementById(STYLE_ID)?.remove();
}

function normalize(value: string): string | null {
  const v = value.trim();
  if (/^\d+\s+\d+%\s+\d+%$/.test(v)) return v;
  if (/^#[0-9a-fA-F]{6}$/.test(v)) return hexToHsl(v);
  return null;
}

export function hexToHsl(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
    }
    h /= 6;
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

export function hslToHex(hsl: string): string {
  const [hStr, sStr, lStr] = hsl.split(/\s+/);
  const h = parseFloat(hStr) / 360;
  const s = parseFloat(sStr) / 100;
  const l = parseFloat(lStr) / 100;
  const hue2rgb = (p: number, q: number, t: number) => {
    if (t < 0) t += 1; if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const r = Math.round(hue2rgb(p, q, h + 1 / 3) * 255);
  const g = Math.round(hue2rgb(p, q, h) * 255);
  const b = Math.round(hue2rgb(p, q, h - 1 / 3) * 255);
  const toHex = (n: number) => n.toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function derivedForeground(hsl: string): string {
  const l = parseFloat(hsl.split(/\s+/)[2]);
  return l > 60 ? "215 28% 17%" : "0 0% 100%";
}