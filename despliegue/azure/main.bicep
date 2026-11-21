param location string = resourceGroup().location
param appName string
param storageName string
param appServicePlanName string = '${appName}-plan'

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: appServicePlanName
  location: location
  kind: 'linux'
  sku: {
    name: 'B1'
    tier: 'Basic'
    size: 'B1'
    capacity: 1
  }
  properties: {
    reserved: true
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource app 'Microsoft.Web/sites@2023-12-01' = {
  name: appName
  location: location
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'bash despliegue/azure/startup.sh'
      alwaysOn: false
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      healthCheckPath: '/api/estado'
      appSettings: [
        { name: 'JACOMIND_DB'; value: '/home/data/jacomind.sqlite3' },
        { name: 'JACOMIND_VAR'; value: '/home/data/var' },
        { name: 'JACOMIND_SALIDA'; value: '/home/data/salida' },
        { name: 'JACOMIND_DATOS'; value: '/home/data/datos' },
        { name: 'JACOMIND_COOKIE_SEGURA'; value: '1' },
        { name: 'JACOMIND_LLM'; value: '0' },
        { name: 'WEBSITE_HTTPLOGGING_RETENTION_DAYS'; value: '7' }
      ]
    }
  }
}

output appName string = app.name
output defaultHostName string = app.properties.defaultHostName
output storageAccountName string = storage.name
