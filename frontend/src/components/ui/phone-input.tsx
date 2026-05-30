import * as React from "react";
import PhoneInputBase, { isValidPhoneNumber, type Country } from "react-phone-number-input";
import "react-phone-number-input/style.css";
import { cn } from "@/lib/utils";

interface PhoneInputProps {
  value: string;
  onChange: (value: string) => void;
  defaultCountry?: Country;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  invalid?: boolean;
}

/**
 * Phone input with country selector and live E.164 validation.
 * Always returns E.164 ("+525512345678") or empty string.
 */
export function PhoneInput({
  value,
  onChange,
  defaultCountry = "MX",
  placeholder = "Número de WhatsApp",
  className,
  disabled,
  invalid,
}: PhoneInputProps) {
  return (
    <PhoneInputBase
      international
      countryCallingCodeEditable={false}
      defaultCountry={defaultCountry}
      value={value || undefined}
      onChange={(v) => onChange(v ?? "")}
      placeholder={placeholder}
      disabled={disabled}
      className={cn(
        "wx-phone-input flex h-9 w-full items-center gap-2 rounded-md border bg-background px-3 text-sm",
        "focus-within:outline-none focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-1",
        invalid ? "border-destructive focus-within:ring-destructive" : "border-input",
        disabled && "opacity-50 cursor-not-allowed",
        className,
      )}
    />
  );
}

export { isValidPhoneNumber };