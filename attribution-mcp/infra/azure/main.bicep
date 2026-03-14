// infra/azure/main.bicep
// Attribution MCP — Azure Container Apps deployment
// Resources: ACR, Container Apps Environment, MCP App, Agent App, Key Vault, UAMI

@description('Base name for all resources')
param baseName string = 'attribution'

@description('Azure region')
param location string = resourceGroup().location

@description('Image tag to deploy')
param imageTag string = 'latest'

// ── Secrets ───────────────────────────────────────────────
@secure() param snowflakeAccount   string
@secure() param snowflakeUser      string
@secure() param snowflakePassword  string
param snowflakeWarehouse  string
param snowflakeDatabase   string
param snowflakeSchema     string = 'PUBLIC'
param snowflakeRole       string = ''

// Attribution config
param attrTouchpointsTable string = 'ATTRIBUTION.TOUCHPOINTS'
param attrConversionsTable  string = 'ATTRIBUTION.CONVERSIONS'
param attrSessionsTable     string = 'ATTRIBUTION.SESSIONS'
param attrSpendTable        string = 'ATTRIBUTION.CHANNEL_SPEND'
param attrLookbackDays      string = '30'
param attrHalflife          string = '7.0'
param attrDefaultModel      string = 'linear'

@secure() param openaiApiKey string
param openaiModel string = 'gpt-4o'

// ── Resource names ────────────────────────────────────────
var acrName          = '${baseName}acr'
var logWorkspaceName = '${baseName}-logs'
var envName          = '${baseName}-env'
var kvName           = '${baseName}-kv'
var mcpAppName       = '${baseName}-mcp'
var agentAppName     = '${baseName}-agent'
var uamiName         = '${baseName}-id'

// ── Managed Identity ──────────────────────────────────────
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: uamiName
  location: location
}

// ── Container Registry ────────────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Log Analytics ─────────────────────────────────────────
resource logs 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logWorkspaceName
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

// ── Container Apps Environment ────────────────────────────
resource caEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

// ── Key Vault ─────────────────────────────────────────────
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: tenant().tenantId
    enableRbacAuthorization: true
  }
}

resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, uami.id, 'KVSecretsUser')
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource secretSnowflakePwd 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'SNOWFLAKE-PASSWORD'
  properties: { value: snowflakePassword }
}

resource secretOpenAI 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'OPENAI-API-KEY'
  properties: { value: openaiApiKey }
}

// ── Shared non-secret env ─────────────────────────────────
var sharedEnv = [
  { name: 'SNOWFLAKE_ACCOUNT',          value: snowflakeAccount }
  { name: 'SNOWFLAKE_USER',             value: snowflakeUser }
  { name: 'SNOWFLAKE_WAREHOUSE',        value: snowflakeWarehouse }
  { name: 'SNOWFLAKE_DATABASE',         value: snowflakeDatabase }
  { name: 'SNOWFLAKE_SCHEMA',           value: snowflakeSchema }
  { name: 'SNOWFLAKE_ROLE',             value: snowflakeRole }
  { name: 'ATTR_TOUCHPOINTS_TABLE',     value: attrTouchpointsTable }
  { name: 'ATTR_CONVERSIONS_TABLE',     value: attrConversionsTable }
  { name: 'ATTR_SESSIONS_TABLE',        value: attrSessionsTable }
  { name: 'ATTR_SPEND_TABLE',           value: attrSpendTable }
  { name: 'ATTR_LOOKBACK_DAYS',         value: attrLookbackDays }
  { name: 'ATTR_TIME_DECAY_HALFLIFE',   value: attrHalflife }
  { name: 'ATTR_DEFAULT_MODEL',         value: attrDefaultModel }
]

// ── MCP Server Container App ───────────────────────────────
resource mcpApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: mcpAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    environmentId: caEnv.id
    configuration: {
      ingress: { external: false, targetPort: 8001, transport: 'http' }
      registries: [{ server: acr.properties.loginServer, identity: uami.id }]
      secrets: [{
        name: 'snowflake-password'
        keyVaultUrl: secretSnowflakePwd.properties.secretUri
        identity: uami.id
      }]
    }
    template: {
      containers: [{
        name: 'attribution-mcp'
        image: '${acr.properties.loginServer}/attribution-mcp:${imageTag}'
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: concat(sharedEnv, [
          { name: 'SNOWFLAKE_PASSWORD', secretRef: 'snowflake-password' }
        ])
      }]
      scale: { minReplicas: 1, maxReplicas: 5 }
    }
  }
}

// ── Agent Container App ────────────────────────────────────
resource agentApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: agentAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    environmentId: caEnv.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'http' }
      registries: [{ server: acr.properties.loginServer, identity: uami.id }]
      secrets: [{
        name: 'openai-api-key'
        keyVaultUrl: secretOpenAI.properties.secretUri
        identity: uami.id
      }]
    }
    template: {
      containers: [{
        name: 'attribution-agent'
        image: '${acr.properties.loginServer}/attribution-agent:${imageTag}'
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'OPENAI_API_KEY',  secretRef: 'openai-api-key' }
          { name: 'OPENAI_MODEL',    value: openaiModel }
          { name: 'MCP_SERVER_URL',  value: 'https://${mcpApp.properties.configuration.ingress.fqdn}/sse' }
        ]
      }]
      scale: { minReplicas: 1, maxReplicas: 10 }
    }
  }
}

// ── Outputs ───────────────────────────────────────────────
output agentUrl       string = 'https://${agentApp.properties.configuration.ingress.fqdn}'
output mcpToolsUrl    string = 'https://${mcpApp.properties.configuration.ingress.fqdn}/tools'
output acrLoginServer string = acr.properties.loginServer
output keyVaultName   string = kv.name
