/** Human-readable descriptions for audit actions (the server stores stable machine codes). */
const ACTIONS: Record<string, string> = {
  "tenant.created": "Institution created",
  "tenant.suspended": "Portal suspended by ScoreCode",
  "tenant.reactivated": "Portal reactivated by ScoreCode",
  "tenant.plan_changed": "Plan changed",
  "tenant.override_set": "Plan limit adjusted by ScoreCode",
  "tenant.ownership_transferred": "Ownership transferred",
  "settings.updated": "Institution settings updated",
  "branding.updated": "Branding updated",
  "branding.logo_updated": "Logo uploaded",
  "branding.logo_removed": "Logo removed",
  "user.invited": "Staff member invited",
  "user.invite_resent": "Invitation re-sent",
  "user.invite_accepted": "Invitation accepted",
  "user.role_changed": "Role changed",
  "user.disabled": "Account disabled",
  "user.enabled": "Account re-enabled",
  "user.password_changed": "Password changed",
  "user.password_reset": "Password reset by email",
  "user.login_locked": "Account temporarily locked after failed sign-ins",
  "auth.login": "Signed in",
  "student.activated": "Student activated their account",
};

export function describeAction(action: string): string {
  return ACTIONS[action] ?? action.replace(/[._]/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const ACTION_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All activity" },
  { value: "settings.", label: "Settings" },
  { value: "branding.", label: "Branding" },
  { value: "user.", label: "People & accounts" },
  { value: "auth.", label: "Sign-ins" },
  { value: "tenant.", label: "Plan & institution" },
];
