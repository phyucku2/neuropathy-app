/**
 * About screen — auth-less (ADR-0032). App identity, the non-diagnostic posture
 * (mirrors ADR-0016 wording), a plain-language description of what the app does,
 * a cross-link to Privacy, a support placeholder, and the IP/licensee line
 * (ADR-0001: owner holds the IP, BioMech Health is a licensee). Static + PHI-free.
 */

import { Link } from 'react-router-dom';
import { InfoLayout } from './InfoLayout';

// Mirror of the app's fixed non-diagnostic disclaimer (ADR-0016). Kept as a literal
// (not imported from the clinician feature) so this auth-less screen stays
// self-contained; the wording must not drift from NonDiagnosticNote.
const NON_DIAGNOSTIC_TEXT = 'Trends support clinical judgment; they are not a diagnosis.';

// Placeholder until the go-to-market support channel is confirmed (see
// docs/mobile/play-listing-pack.md). Not a live address.
const SUPPORT_CONTACT = 'support@[your-domain] (placeholder — set before store submission)';

export function AboutPage() {
  return (
    <InfoLayout title="About Neuropathy">
      <p className="eyebrow">About</p>
      <h1>Neuropathy</h1>
      <p className="muted">Version {__APP_VERSION__}</p>

      <div className="card">
        <h2>Not a diagnosis</h2>
        <p>{NON_DIAGNOSTIC_TEXT}</p>
        <p className="muted" style={{ marginTop: 8 }}>
          Neuropathy is a tracking and decision-support tool. It does not diagnose, treat, or
          prevent any disease, and it is not a substitute for professional medical advice. Always
          talk to your care team about what your trends mean for you.
        </p>
      </div>

      <div className="card">
        <h2>What Neuropathy does</h2>
        <p className="muted">
          Neuropathy brings your balance and gait reports, lab results, and daily function check-ins
          together in one place, so you can see how they change over time. It turns those readings
          into plain-language trends and an explainable direction — always naming what each signal
          is based on, and saying &ldquo;not enough data yet&rdquo; instead of guessing.
        </p>
        <p className="muted" style={{ marginTop: 8 }}>
          Your data stays private until you choose to share it. You hold the switch that lets a
          clinic see your information, and you can turn it off at any time.
        </p>
      </div>

      <div className="card">
        <h2>Privacy</h2>
        <p className="muted">
          We collect only what the app needs to work, never sell your information, and use no
          advertising or analytics trackers.
        </p>
        <p style={{ marginTop: 8 }}>
          <Link className="link" to="/privacy">
            Read the privacy summary
          </Link>
        </p>
      </div>

      <div className="card">
        <h2>Support</h2>
        <p className="muted">Questions or a problem with the app? Contact {SUPPORT_CONTACT}.</p>
      </div>

      <p className="muted centered" style={{ marginTop: 8 }}>
        Neuropathy and its underlying methods are owned by Advanced Health and Wellness Group.
        BioMech Health is a licensee.
      </p>
    </InfoLayout>
  );
}
