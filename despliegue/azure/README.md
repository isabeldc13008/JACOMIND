# Staging en Azure

Esta configuración despliega JACOMIND sobre Azure App Service Linux y mantiene la arquitectura actual de la aplicación: Python, SQLite y los datos de escritura bajo `/home/data`. Está pensada para staging con datos sintéticos; no es todavía una configuración de producción.

## Crear recursos

```bash
az group create --name rg-jacomind-staging --location eastus2
az deployment group create \
  --resource-group rg-jacomind-staging \
  --template-file despliegue/azure/main.bicep \
  --parameters appName=jacomind-staging storageName=jacomindstaging<unico>
```

El plan B1 usa crédito de Azure for Students. Si el portal ofrece un plan gratuito compatible con Linux, puede sustituirse después de verificar sus límites; el B1 es la opción reproducible para Python 3.12.

## Desplegar código

El workflow `.github/workflows/azure-staging.yml` publica `main` después de pasar las pruebas. Configura en GitHub el environment `azure-staging` con:

- `AZURE_CREDENTIALS`: credencial JSON de un principal de servicio limitado al resource group.
- `AZURE_RESOURCE_GROUP`: `rg-jacomind-staging`.
- `AZURE_WEBAPP_NAME`: nombre de la App Service.

No guardar claves de Gemini, Anthropic ni archivos `.env` en Git. Para el primer staging se mantiene `JACOMIND_LLM=0` y el acceso de demostración solo debe usarse con datos sintéticos.

## Datos de práctica

Después del primer despliegue, copiar los datos a `/home/data/datos` desde una sesión administrativa de App Service o publicar el cierre mediante la API. No versionar `Green_Services_Recursos_de_Prueba` ni datos empresariales.

## Verificación

```bash
curl -fsS https://jacomind-staging.azurewebsites.net/api/estado
```

Comprobar también `/app/`, el certificado HTTPS, `Set-Cookie` con `Secure` y el cierre de octubre antes de cambiar cualquier configuración de identidad.
