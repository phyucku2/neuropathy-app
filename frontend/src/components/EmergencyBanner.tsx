/**
 * The persistent non-urgent / 911 banner (ADR-0047, mirroring ADR-0045/0046): EVERY
 * caregiver-facing screen carries this framing — the product is a periodic wellness
 * trend, never real-time monitoring, never an emergency channel. Reuses the existing
 * .emergency-banner treatment (ADR-0045 P2); non-dismissible by design.
 *
 * The default wording matches the backend's EMERGENCY_NOTICE
 * (backend/app/schemas/caregiver.py) so the two surfaces can never drift; a caller
 * with a co-located, surface-specific line passes it as children.
 */

import type { ReactNode } from 'react';

/** The backend's caregiver EMERGENCY_NOTICE, verbatim. */
export const EMERGENCY_NOTICE =
  "This isn't for emergencies. If something's wrong right now, call 911.";

export function EmergencyBanner({ children }: { children?: ReactNode }) {
  return (
    <div className="emergency-banner" role="note" aria-label="Emergency information">
      {children ?? (
        <>
          <b>This isn&apos;t for emergencies.</b> If something&apos;s wrong right now, call 911.
        </>
      )}
    </div>
  );
}
