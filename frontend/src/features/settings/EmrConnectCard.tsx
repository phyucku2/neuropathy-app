/**
 * "Health record connections" (ADR-0028) — the patient EMR-connect entry point.
 *
 * Provider picker over GET /emr/providers (server-side search), then POST /emr/connect:
 * the pending `state` is persisted (sessionStorage, pendingConnect.ts) and the returned
 * authorize URL opens via the platform seam (web: full-page redirect; native: system
 * browser — never the in-app WebView). The EMR redirects to /emr/callback, where
 * EmrCallbackPage relays code+state to the bearer-authenticated backend callback.
 *
 * Gated by the `emr_connect` capability the API already exposes — a UI hint only
 * (ADR-0013: the server is the authority; its 409 is surfaced verbatim if it refuses).
 * The API has no EMR-connections LIST endpoint yet (gap recorded in ADR-0028), so this
 * card starts connections; the post-connect confirmation lives on /emr/callback.
 */

import { useCallback, useState } from 'react';
import { messageFor } from '../../api/client';
import { getCapabilities, getEmrProviders, startEmrConnect } from '../../api/endpoints';
import type { EmrProviderOut } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { useApi } from '../../lib/useApi';
import { openAuthorizeUrl } from '../../native/externalBrowser';
import { savePendingConnect } from '../emr/pendingConnect';

function ProviderRow({
  provider,
  onConnect,
  disabled,
  connecting,
}: {
  provider: EmrProviderOut;
  onConnect: (provider: EmrProviderOut) => void;
  disabled: boolean;
  connecting: boolean;
}) {
  return (
    <div className="src">
      <span className="ic" style={{ background: 'var(--color-brand-sky)' }} aria-hidden="true">
        🏥
      </span>
      <div className="info">
        <b>{provider.name}</b>
        <small>{provider.vendor}</small>
      </div>
      {provider.sandbox_fhir_base === null ? (
        // No public endpoint until the app is registered with this vendor — honest
        // instead of a Connect that can only fail (the API would 422).
        <span className="pill off">Not available yet</span>
      ) : (
        <button
          type="button"
          className="btn-inline"
          style={{ width: 'auto', marginTop: 0 }}
          disabled={disabled}
          aria-label={`Connect ${provider.name}`}
          onClick={() => {
            onConnect(provider);
          }}
        >
          {connecting ? 'Opening…' : 'Connect'}
        </button>
      )}
    </div>
  );
}

export function EmrConnectCard() {
  const { data: capabilityData, loading: capabilitiesLoading } = useApi(getCapabilities);
  const [query, setQuery] = useState('');
  const providersFetcher = useCallback(() => getEmrProviders(query), [query]);
  const { data: providers, error, loading } = useApi(providersFetcher);
  const [startError, setStartError] = useState<string | null>(null);
  const [connectingKey, setConnectingKey] = useState<string | null>(null);

  const emrConnect = capabilityData?.capabilities.find((row) => row.key === 'emr_connect');
  // UI hint only — the server enforces the toggle on connect AND callback (ADR-0020).
  const toggledOff = emrConnect !== undefined && !emrConnect.active;

  const connect = async (provider: EmrProviderOut) => {
    setStartError(null);
    setConnectingKey(provider.key);
    try {
      const started = await startEmrConnect({ provider_key: provider.key });
      // Persist BEFORE leaving the page: the callback route verifies the EMR's echoed
      // state against this value and refuses anything it did not start.
      savePendingConnect({
        state: started.state,
        connectionId: started.connection_id,
        providerName: provider.name,
      });
      await openAuthorizeUrl(started.authorize_url);
      // On web the page navigates away here; on native the system browser is now in
      // front. Keep the button in its busy state until the flow returns.
    } catch (cause) {
      // A 409 (emr_connect off) or 422 carries the server's own explanation — verbatim.
      setStartError(messageFor(cause));
      setConnectingKey(null);
    }
  };

  return (
    <>
      <h2>Health record connections</h2>
      {startError !== null && <ErrorNotice>{startError}</ErrorNotice>}
      <div className="card">
        {capabilitiesLoading ? (
          <Loading label="Loading health record connections…" />
        ) : toggledOff ? (
          <p className="muted" style={{ margin: 0 }}>
            Medical record connection is turned off in your sources above, so new health record
            connections can’t be started.
          </p>
        ) : (
          <>
            <div className="field">
              <label htmlFor="emr-provider-search">Search for your provider</label>
              <input
                id="emr-provider-search"
                type="search"
                value={query}
                placeholder="Epic, Cerner, athenahealth…"
                onChange={(event) => {
                  setQuery(event.target.value);
                }}
              />
            </div>
            {loading && providers === null && <Loading label="Loading providers…" />}
            {error !== null && <ErrorNotice>{error}</ErrorNotice>}
            {providers !== null && providers.length === 0 && (
              <p className="muted" style={{ margin: 0 }}>
                No providers match your search.
              </p>
            )}
            {providers !== null &&
              providers.map((provider) => (
                <ProviderRow
                  key={provider.key}
                  provider={provider}
                  disabled={connectingKey !== null}
                  connecting={connectingKey === provider.key}
                  onConnect={(row) => {
                    void connect(row);
                  }}
                />
              ))}
          </>
        )}
      </div>
      <p className="muted centered">
        You’ll sign in on your provider’s own site — this app never sees your portal password.
      </p>
    </>
  );
}
