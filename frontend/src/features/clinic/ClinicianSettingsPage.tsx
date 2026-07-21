/**
 * Settings — the clinician account's own settings surface (reached from the header's
 * Settings link, clinician area only). Holds account security: today that is two-step
 * verification enrollment (§1B C6). The PATIENT settings surface (/settings, "Sources")
 * is a different screen and is untouched by this page.
 */

import { MfaEnrollmentCard } from './MfaEnrollmentCard';

export function ClinicianSettingsPage() {
  return (
    <div>
      <h1>Settings</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Security settings for your clinician account.
      </p>
      <MfaEnrollmentCard />
    </div>
  );
}
