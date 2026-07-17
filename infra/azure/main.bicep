// =============================================================================
// neuropathy-app — Azure deployment (parallel to the Render blueprint render.yaml).
//
// Target: Azure Container Apps + Azure Database for PostgreSQL Flexible Server.
// This replicates the Render blueprint's INTENT on Azure:
//   - backend  : FastAPI (Gunicorn + Uvicorn) from backend/Dockerfile, INTERNAL ingress
//   - frontend : nginx SPA from frontend/Dockerfile, EXTERNAL ingress, reverse-proxies
//                the API to the backend over the environment's internal DNS (same-origin
//                -> no CORS; the backend ships none)
//   - db       : Azure Database for PostgreSQL Flexible Server + a database
//   - migrate  : a Container Apps *Job* that runs `alembic upgrade head` on the SAME
//                backend image, invoked manually BEFORE the backend serves (the app never
//                self-migrates; the entrypoint does not migrate on boot -> no double-run)
//
// NOTHING here is a committed secret. Every credential is a parameter marked @secure()
// (operator supplies at deploy time) or is constructed at deploy time into a Container
// Apps *secret* (never an output, never in git). See docs/ops/deploy-azure.md.
//
// IMPORTANT — HIPAA/PHI: Azure is HIPAA-eligible, but you MUST have a signed BAA with
// Microsoft (Microsoft Product Terms / DPA) BEFORE any real PHI flows. See the runbook.
//
// IMPORTANT — DATABASE_URL async scheme + SSL (the one manual wire, automated here):
//   The app's engine and Alembic require the async driver scheme `postgresql+asyncpg://`
//   (backend/app/db/session.py, backend/alembic/env.py). Azure Postgres Flexible Server
//   ENFORCES TLS, and asyncpg (via SQLAlchemy's dialect, which passes URL query params
//   straight to asyncpg.connect) takes SSL as `?ssl=require` — NOT libpq's `?sslmode=`
//   (asyncpg.connect has an `ssl` kwarg, no `sslmode` kwarg). This template builds
//   DATABASE_URL as
//     postgresql+asyncpg://<login>:<password>@<server-fqdn>:5432/<db>?ssl=require
//   into a Container Apps secret. Override with `databaseUrlOverride` if you manage the
//   connection string yourself.
//
// api-versions below are ones known-good at authoring time; bump deliberately.
// =============================================================================

// ------------------------------ Parameters ----------------------------------

@description('Azure region for all resources. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Short name prefix for all resources (lowercase alphanumerics; keep < 20 chars).')
@minLength(2)
@maxLength(20)
param namePrefix string = 'neuropathy'

// --- Container images (build + push these first; see the runbook) ------------
@description('Full backend image reference, e.g. myacr.azurecr.io/neuropathy-backend:2024-07-17. Built from backend/Dockerfile.')
param backendImage string

@description('Full frontend image reference, e.g. myacr.azurecr.io/neuropathy-frontend:2024-07-17. Built from frontend/Dockerfile.')
param frontendImage string

// --- Container registry (leave server blank to pull from a public registry) --
@description('Container registry login server, e.g. myacr.azurecr.io. Blank = images are on a public registry (no auth).')
param registryServer string = ''

@description('Container registry username (e.g. ACR admin user or a token name). Ignored when registryServer is blank.')
param registryUsername string = ''

@description('Container registry password / token. Ignored when registryServer is blank.')
@secure()
param registryPassword string = ''

// --- PostgreSQL Flexible Server ----------------------------------------------
@description('PostgreSQL admin login name (used in DATABASE_URL). Not "azure_superuser".')
param postgresAdminLogin string = 'neuro'

@description('PostgreSQL admin password. Supply at deploy time; never commit.')
@secure()
param postgresAdminPassword string

@description('Application database name.')
param databaseName string = 'neuropathy'

@description('PostgreSQL major version.')
@allowed([ '16', '15', '14', '13' ])
param postgresVersion string = '16'

@description('Flexible Server compute SKU name, e.g. Standard_B1ms (Burstable) or Standard_D2ds_v5 (GeneralPurpose).')
param postgresSkuName string = 'Standard_B1ms'

@description('Flexible Server compute tier.')
@allowed([ 'Burstable', 'GeneralPurpose', 'MemoryOptimized' ])
param postgresSkuTier string = 'Burstable'

@description('Flexible Server storage size in GB.')
param postgresStorageGb int = 32

// --- Application secrets (operator supplies; kept out of git) -----------------
@description('JWT signing secret (ADR-0010). REQUIRED for durable auth. Generate: python -c "import secrets; print(secrets.token_urlsafe(48))". Rotating it logs everyone out.')
@secure()
param jwtSecret string

@description('OPTIONAL Fernet key for the DB-backed EMR OAuth token vault (ADR-0017). Blank = EMR tokens stay in a per-process in-memory vault (fail closed). Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())".')
@secure()
param secretStoreKey string = ''

@description('OPTIONAL first-ops bootstrap token (ADR-0019). Blank = clinician provisioning disabled (patient register/login still works). If set, MUST be >= 32 chars or the backend fails closed at startup. Generate: python -c "import secrets; print(secrets.token_urlsafe(48))".')
@secure()
param opsBootstrapToken string = ''

@description('OPTIONAL full DATABASE_URL override. Blank = built from the Postgres server above as postgresql+asyncpg://...?ssl=require. If you set this, it MUST use the postgresql+asyncpg:// scheme and asyncpg SSL semantics (?ssl=require), not libpq ?sslmode=.')
@secure()
param databaseUrlOverride string = ''

// --- App runtime tuning ------------------------------------------------------
@description('Gunicorn worker count (gunicorn.conf.py). Size to the backend container CPU.')
param webConcurrency string = '2'

@description('Backend container CPU (cores). Container Apps requires cpu/memory to pair, e.g. 0.5/1Gi, 1.0/2Gi.')
param backendCpu string = '0.5'

@description('Backend container memory, e.g. 1.0Gi.')
param backendMemory string = '1.0Gi'

@description('Frontend container CPU (cores).')
param frontendCpu string = '0.25'

@description('Frontend container memory, e.g. 0.5Gi.')
param frontendMemory string = '0.5Gi'

@description('Min/Max replicas for the backend.')
param backendMinReplicas int = 1
param backendMaxReplicas int = 3

@description('Min/Max replicas for the frontend.')
param frontendMinReplicas int = 1
param frontendMaxReplicas int = 3

// ------------------------------ Variables ------------------------------------

var logAnalyticsName = '${namePrefix}-logs'
var environmentName = '${namePrefix}-env'
var backendAppName = '${namePrefix}-backend'
var frontendAppName = '${namePrefix}-frontend'
var migrateJobName = '${namePrefix}-migrate'
var postgresServerName = '${namePrefix}-pg-${uniqueString(resourceGroup().id)}'

// The backend listens on $PORT (default 8000; backend/Dockerfile EXPOSE 8000,
// gunicorn.conf.py binds 0.0.0.0:$PORT). Container Apps ingress terminates on 80/443
// and forwards to targetPort.
var backendTargetPort = 8000
var frontendTargetPort = 8080

// Registry wiring is conditional: only emit a registries block + credential secret when
// a private registry server is supplied.
var usePrivateRegistry = !empty(registryServer)

// DATABASE_URL: async scheme + asyncpg SSL. Built from the server unless overridden.
// asyncpg takes `?ssl=require` (SQLAlchemy asyncpg dialect forwards query params to
// asyncpg.connect, which has an `ssl` kwarg, NOT libpq's `sslmode`).
var builtDatabaseUrl = 'postgresql+asyncpg://${postgresAdminLogin}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${databaseName}?ssl=require'
var databaseUrl = empty(databaseUrlOverride) ? builtDatabaseUrl : databaseUrlOverride

// Backend container secrets. The OPTIONAL ones (SECRET_STORE_KEY, OPS_BOOTSTRAP_TOKEN)
// are omitted ENTIRELY when blank rather than set to '' — Container Apps can reject an
// empty-valued secret, and config.py treats an absent var exactly as it treats blank
// (fail-closed defaults). Their env vars are gated the same way (below) so no secretRef
// ever dangles.
var optionalSecrets = concat(
  empty(secretStoreKey) ? [] : [ { name: 'secret-store-key', value: secretStoreKey } ],
  empty(opsBootstrapToken) ? [] : [ { name: 'ops-bootstrap-token', value: opsBootstrapToken } ]
)
var backendAppSecrets = concat([
  { name: 'jwt-secret', value: jwtSecret }
  { name: 'database-url', value: databaseUrl }
], optionalSecrets)

var registrySecret = [
  { name: 'registry-password', value: registryPassword }
]
var backendSecrets = usePrivateRegistry ? concat(backendAppSecrets, registrySecret) : backendAppSecrets
var frontendSecrets = usePrivateRegistry ? registrySecret : []

var registriesBlock = usePrivateRegistry ? [
  {
    server: registryServer
    username: registryUsername
    passwordSecretRef: 'registry-password'
  }
] : []

// Common backend env vars (shared by the server app and the migration job). The optional
// secret-backed vars are included only when their secret exists.
var optionalBackendEnv = concat(
  empty(secretStoreKey) ? [] : [ { name: 'SECRET_STORE_KEY', secretRef: 'secret-store-key' } ],
  empty(opsBootstrapToken) ? [] : [ { name: 'OPS_BOOTSTRAP_TOKEN', secretRef: 'ops-bootstrap-token' } ]
)
var backendEnv = concat([
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
  { name: 'APP_ENV', value: 'production' }
  { name: 'APP_DEBUG', value: 'false' }
  { name: 'WEB_CONCURRENCY', value: webConcurrency }
  // PORT defaults to 8000 in gunicorn.conf.py; set explicitly to match ingress.targetPort.
  { name: 'PORT', value: string(backendTargetPort) }
], optionalBackendEnv)

// ------------------------------ Log Analytics --------------------------------
// Container Apps environments require a Log Analytics workspace for app logs.

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ------------------------- Container Apps environment ------------------------

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// --------------------- PostgreSQL Flexible Server + database ------------------

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = {
  name: postgresServerName
  location: location
  sku: {
    name: postgresSkuName
    tier: postgresSkuTier
  }
  properties: {
    version: postgresVersion
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: {
      storageSizeGB: postgresStorageGb
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    // Public access with an "allow Azure services" firewall rule (below) is the simplest
    // wire that lets Container Apps reach the DB. For a hardened PHI posture prefer PRIVATE
    // access (VNet integration / Private DNS) — see the runbook's "open decisions".
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = {
  parent: postgres
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Special rule: start=end=0.0.0.0 means "allow public network access from Azure services
// and resources" (the Azure-internal allowance). Container Apps egress reaches the server
// through this. Tighten/replace with private networking for production PHI.
resource pgAllowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = {
  parent: postgres
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ------------------------------ Backend app ----------------------------------
// INTERNAL ingress: only the frontend (and the migration job) reach it, over the
// environment's internal DNS. Not internet-exposed.

resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: backendAppName
  location: location
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: backendTargetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: registriesBlock
      secrets: backendSecrets
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: {
            cpu: json(backendCpu)
            memory: backendMemory
          }
          env: backendEnv
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: backendTargetPort
              }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/readyz'
                port: backendTargetPort
              }
              initialDelaySeconds: 5
              periodSeconds: 15
              timeoutSeconds: 3
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: backendMinReplicas
        maxReplicas: backendMaxReplicas
      }
    }
  }
  dependsOn: [
    database
    pgAllowAzure
  ]
}

// ------------------------------ Frontend app ---------------------------------
// EXTERNAL ingress. Same-origin reverse-proxy: API_BASE_URL="" and BACKEND_ORIGIN set to
// the backend's INTERNAL FQDN. nginx proxies /auth, /observations, /trajectory, ... to it.
//
// NOTE (open decision — see runbook): frontend/nginx.conf.template pins
// `resolver 127.0.0.11` (Docker's embedded DNS) for its variable proxy_pass. That address
// does not exist in Container Apps. Frontend/backend logic is intentionally NOT modified
// here; if the reverse-proxy fails DNS resolution in your environment, see the runbook's
// "nginx resolver" note for the two supported workarounds.

resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: frontendAppName
  location: location
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: frontendTargetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: registriesBlock
      secrets: frontendSecrets
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          resources: {
            cpu: json(frontendCpu)
            memory: frontendMemory
          }
          env: [
            // Empty = same-origin: nginx reverse-proxies the API to BACKEND_ORIGIN.
            { name: 'API_BASE_URL', value: '' }
            // Internal FQDN of the backend on the Container Apps environment. Internal
            // ingress serves plain HTTP on port 80, which nginx's `proxy_pass http://...`
            // targets by default (no port suffix needed).
            { name: 'BACKEND_ORIGIN', value: backendApp.properties.configuration.ingress.fqdn }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: frontendTargetPort
              }
              initialDelaySeconds: 5
              periodSeconds: 30
              timeoutSeconds: 3
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: frontendMinReplicas
        maxReplicas: frontendMaxReplicas
      }
    }
  }
}

// ------------------------- Migration job (alembic) ---------------------------
// A manually-triggered Container Apps Job that runs `alembic upgrade head` on the SAME
// backend image (WORKDIR /app holds alembic.ini + alembic/; the venv is on PATH). The
// image entrypoint does NOT migrate on boot, so this is the ONLY place migrations run ->
// no double-run. Invoke it BEFORE the backend serves new schema:
//   az containerapp job start -n <migrateJobName> -g <rg>
// See docs/ops/deploy-azure.md.

resource migrateJob 'Microsoft.App/jobs@2024-03-01' = {
  name: migrateJobName
  location: location
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 600
      replicaRetryLimit: 1
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registriesBlock
      secrets: backendSecrets
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: backendImage
          // Override the image CMD (gunicorn) with the migration one-shot. The image
          // ENTRYPOINT (docker-entrypoint.sh) still runs and `exec`s this command.
          command: [ 'alembic' ]
          args: [ 'upgrade', 'head' ]
          resources: {
            cpu: json(backendCpu)
            memory: backendMemory
          }
          env: [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'APP_ENV', value: 'production' }
            { name: 'APP_DEBUG', value: 'false' }
          ]
        }
      ]
    }
  }
  dependsOn: [
    database
    pgAllowAzure
  ]
}

// ------------------------------ Outputs --------------------------------------

@description('Public URL of the frontend SPA (the app entry point).')
output frontendUrl string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'

@description('Internal FQDN of the backend (reachable only inside the Container Apps environment).')
output backendInternalFqdn string = backendApp.properties.configuration.ingress.fqdn

@description('PostgreSQL server FQDN.')
output postgresFqdn string = postgres.properties.fullyQualifiedDomainName

@description('Name of the migration job to invoke with `az containerapp job start`.')
output migrateJobName string = migrateJob.name

@description('Whether DATABASE_URL was built from the provisioned server (false = you passed databaseUrlOverride).')
output databaseUrlWasBuilt bool = empty(databaseUrlOverride)
