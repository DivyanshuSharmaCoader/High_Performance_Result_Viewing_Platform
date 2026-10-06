import type { components } from "./schema";

/** Response/request types generated from backend/openapi.json (regenerate with `make openapi`). */
export type Schemas = components["schemas"];
export type Me = Schemas["MeOut"];
export type SessionOut = Schemas["SessionOut"];
export type Staff = Schemas["StaffOut"];
export type BrandingOut = Schemas["BrandingOut"];
export type SettingsOut = Schemas["SettingsOut"];
export type SubscriptionOut = Schemas["SubscriptionOut"];
export type AuditEntry = Schemas["AuditEntry"];
export type JobOut = Schemas["JobOut"];
export type TenantRow = Schemas["TenantRow"];
export type PlatformMe = Schemas["PlatformMeOut"];

export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
  total?: number | null;
}

export interface TenantConfig {
  tenant: { slug: string; name: string };
  branding: {
    display_name: string;
    short_name: string | null;
    logo_url: string | null;
    logo_version: number;
    login_heading: string | null;
    login_message: string | null;
    footer_text: string | null;
    support_email: string | null;
    show_powered_by: boolean;
    tokens: {
      primary: string;
      primary_contrast: string;
      primary_ink: string;
      accent: string;
      accent_contrast: string;
      font_family: string;
    };
  };
  settings: { student_activation_mode: string; locale: string };
  features: Record<string, unknown>;
}
export type Onboarding = Schemas["OnboardingOut"];
export type OnboardingStep = Schemas["OnboardingStep"];
export type LimitUsage = Schemas["LimitUsage"];
