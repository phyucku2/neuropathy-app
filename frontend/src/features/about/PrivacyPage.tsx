/**
 * Privacy summary screen — auth-less (ADR-0026/ADR-0032). An in-app rendering of
 * docs/legal/privacy-policy-draft.md, adapted into readable summary copy. It is
 * explicitly a SUMMARY that points to the full policy URL placeholder, and it
 * keeps the draft's honesty: the full policy is reviewed by counsel before
 * publication. Static content only — no data calls, no PHI.
 */

import { Link } from 'react-router-dom';
import { InfoLayout } from './InfoLayout';

// Placeholder — the counsel-approved policy lives at a public URL at store
// submission (docs/mobile/play-listing-pack.md checklist). Not a live link.
const FULL_POLICY_URL = '[full privacy policy URL — set before store submission]';
const PRIVACY_CONTACT = 'Advanced Health and Wellness Group — privacy@[your-domain] (placeholder)';

export function PrivacyPage() {
  return (
    <InfoLayout title="Privacy summary">
      <p className="eyebrow">Privacy</p>
      <h1>Your privacy, in plain language</h1>
      <p className="muted">
        This is a short summary of how Neuropathy handles your information. It is not the complete
        policy: the full, counsel-reviewed privacy policy is published at {FULL_POLICY_URL} before
        release, and it governs if the two ever differ.
      </p>

      <div className="card">
        <h2>What we collect</h2>
        <ul className="muted">
          <li>
            <strong>Account information</strong> — your name and email, used to create and secure
            your account. Passwords are stored only as modern one-way hashes.
          </li>
          <li>
            <strong>Health information you add</strong> — daily function check-ins, lab results you
            import from your medical record after you authorize the connection, and balance/gait
            measurements from reports you upload.
          </li>
          <li>
            <strong>Nothing else</strong> — no location, contacts, advertising identifiers, or usage
            analytics. The app contains no advertising or analytics trackers.
          </li>
        </ul>
      </div>

      <div className="card">
        <h2>How your information is used</h2>
        <p className="muted">
          Your information is used only to provide the app to you: showing your trends, computing
          your explainable trajectory, and — only if you turn sharing on — making your data visible
          to the clinic you authorized. We do not sell your information, and we do not share it with
          third parties for marketing.
        </p>
      </div>

      <div className="card">
        <h2>Your controls</h2>
        <ul className="muted">
          <li>
            <strong>You hold the sharing switch.</strong> Clinician access needs your consent and
            stops the moment you turn it off — your clinic cannot override it.
          </li>
          <li>Connections can be revoked at any time, and revoking is never blocked.</li>
          <li>
            <strong>Account and data deletion</strong> is available in the app under Settings, and
            removes your account and health data.
          </li>
        </ul>
      </div>

      <div className="card">
        <h2>Security</h2>
        <ul className="muted">
          <li>
            All network traffic is encrypted in transit; the app refuses unencrypted connections.
          </li>
          <li>
            On your device, your session credential is kept in the operating system&rsquo;s
            hardware-backed secure storage and, where available, protected by your biometric or
            device passcode. App data is excluded from device backups.
          </li>
          <li>On our servers, access to your information is consent-gated and audited.</li>
        </ul>
      </div>

      <div className="card">
        <h2>What Neuropathy is not</h2>
        <p className="muted">
          Neuropathy is a tracking and decision-support tool. It does not diagnose, treat, or
          prevent any disease, and it is not a substitute for professional medical advice.
        </p>
      </div>

      <div className="card">
        <h2>Contact</h2>
        <p className="muted">Questions about your privacy? Contact {PRIVACY_CONTACT}.</p>
      </div>

      <p className="centered" style={{ marginTop: 8 }}>
        <Link className="link" to="/about">
          Back to About
        </Link>
      </p>
    </InfoLayout>
  );
}
