/**
 * Caregiver Companion E2E (ADR-0047): the REAL cross-role journey in two browser
 * contexts sharing one mock-backend store — the patient mints an invite code, the
 * loved one registers with it (claim), the patient explicitly accepts (double
 * opt-in), the caregiver sees the trend; the patient revokes and the caregiver
 * lands back on the neutral state. Every caregiver screen must carry the
 * persistent 911 banner.
 */

import { expect, signedInApp, test } from '../support/fixtures';
import {
  activeCaregiverLink,
  CAREGIVER_CLAIM_ACCEPTED_DETAIL,
  CAREGIVER_ME,
  installApiMocks,
  newCaregiverStore,
  SYNTHETIC_PASSWORD,
} from '../support/mock-api';

const BANNER_TEXT = "If something's wrong right now, call 911.";

test.describe('Caregiver Companion (ADR-0047)', () => {
  test('invite → claim → patient accepts → caregiver sees the trend; revoke → neutral state', async ({
    page,
    browser,
  }) => {
    // ONE store behind both roles: the same statefulness the real backend has.
    const store = newCaregiverStore();
    await signedInApp(page, { caregiverStore: store });

    // 1. The PATIENT mints an invite code on Sources ("Share with a loved one").
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Share with a loved one' })).toBeVisible();
    await page.getByRole('button', { name: 'Create an invite code' }).click();
    const code = await page.locator('.invite-code').innerText();
    expect(code).not.toEqual('');
    // The one-time honesty + expiry are stated with the code.
    await expect(page.getByText(/works once and expires/)).toBeVisible();

    // 2. The LOVED ONE registers with the code in their own browser context.
    const caregiverContext = await browser.newContext();
    const caregiverPage = await caregiverContext.newPage();
    await installApiMocks(caregiverPage, { me: CAREGIVER_ME, caregiverStore: store });
    await caregiverPage.goto('/caregiver/join');
    // The 911 banner rides the join screen too.
    await expect(caregiverPage.getByText(BANNER_TEXT)).toBeVisible();
    await caregiverPage.getByLabel('Invite code').fill(code);
    await caregiverPage.getByLabel('Your name').fill('Casey Example');
    await caregiverPage.getByLabel('Email').fill('casey.example@example.com');
    await caregiverPage.getByLabel('Password').fill(SYNTHETIC_PASSWORD);
    await caregiverPage.getByRole('button', { name: 'Create account & send request' }).click();

    // 3. Double opt-in: the caregiver WAITS — nothing is visible before the patient's yes.
    await expect(
      caregiverPage.getByRole('heading', { name: 'No one is sharing with you yet' }),
    ).toBeVisible();
    await expect(caregiverPage.getByText(BANNER_TEXT)).toBeVisible();

    // 4. The PATIENT sees the pending request by name and explicitly accepts.
    await page.goto('/settings');
    await expect(page.getByText('Waiting for your OK')).toBeVisible();
    await page.getByRole('button', { name: 'Yes, share with Casey Example' }).click();
    await expect(page.getByText('Sharing with')).toBeVisible();
    await expect(page.getByText('Can see their trend only')).toBeVisible();

    // 5. The caregiver now sees the trend: hero + co-located non-diagnostic note + banner.
    await caregiverPage.reload();
    await expect(caregiverPage.getByText('30 Day Score')).toBeVisible();
    await expect(caregiverPage.getByText('74')).toBeVisible();
    await expect(caregiverPage.getByText(/not a diagnosis, and not live monitoring/)).toBeVisible();
    await expect(caregiverPage.getByText(BANNER_TEXT)).toBeVisible();
    // Trends scope only — no Visit-Ready Summary link.
    await expect(
      caregiverPage.getByRole('link', { name: 'See their Visit-Ready Summary' }),
    ).toHaveCount(0);

    // 6. The PATIENT revokes — instant, two-tap, never blockable.
    await page.getByRole('button', { name: 'Stop sharing' }).click();
    await page.getByRole('button', { name: 'Tap again to confirm' }).click();
    await expect(page.getByText('Sharing with')).toHaveCount(0);

    // 7. The caregiver loses access and lands on the NEUTRAL state — no reason leaked.
    await caregiverPage.reload();
    await expect(
      caregiverPage.getByRole('heading', { name: 'No one is sharing with you yet' }),
    ).toBeVisible();
    await expect(caregiverPage.getByText('30 Day Score')).toHaveCount(0);
    await expect(caregiverPage.getByText(BANNER_TEXT)).toBeVisible();

    // 8. A fresh code can be claimed from the home — the 202's fixed sentence, verbatim.
    await page.getByRole('button', { name: 'Create an invite code' }).click();
    // The previous notice stays mounted while the POST resolves — wait for the NEW code.
    await expect(page.locator('.invite-code')).not.toHaveText(code);
    const secondCode = await page.locator('.invite-code').innerText();
    // (getByRole: the claim card's section is ALSO aria-labelled with "…invite code…",
    // so a label substring match would be ambiguous — target the textbox.)
    await caregiverPage.getByRole('textbox', { name: 'Invite code' }).fill(secondCode);
    await caregiverPage.getByRole('button', { name: 'Send my request' }).click();
    await expect(caregiverPage.getByText(CAREGIVER_CLAIM_ACCEPTED_DETAIL)).toBeVisible();

    await caregiverContext.close();
  });

  test('full scope shows the read-only Visit-Ready Summary; trends-only stays neutral', async ({
    page,
  }) => {
    const store = newCaregiverStore();
    const link = activeCaregiverLink('full');
    store.links.push(link);
    await signedInApp(page, { me: CAREGIVER_ME, caregiverStore: store });

    await page.goto('/caregiver');
    await expect(page.getByText('30 Day Score')).toBeVisible();
    await page.getByRole('link', { name: 'See their Visit-Ready Summary' }).click();

    // The SAME shared VisitSummaryView render (ADR-0045), read-only, with the banner.
    await expect(
      page.getByRole('heading', { name: "Pat Example's Visit-Ready Summary" }),
    ).toBeVisible();
    await expect(page.getByRole('heading', { name: 'What changed' })).toBeVisible();
    await expect(page.getByText(BANNER_TEXT)).toBeVisible();
    // Metadata-only EMR note row, exactly as elsewhere (never the note body).
    await expect(page.getByText('Progress note')).toBeVisible();

    // Window picker refetches; the heading is labelled from the payload's own window.
    await page.getByRole('button', { name: '1 year' }).click();
    await expect(page.getByText('1 year summary')).toBeVisible();

    // Trends-only: the summary route is the NEUTRAL not-available state (no scope leak).
    link.scope = 'trends';
    await page.reload();
    await expect(
      page.getByRole('heading', { name: "This isn't available right now" }),
    ).toBeVisible();
  });
});
