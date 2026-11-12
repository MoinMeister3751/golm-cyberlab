# IIS als HTTPS-Reverse-Proxy (Windows Server 2025)

Die Anwendung (waitress) lauscht nur auf `127.0.0.1:8080`. IIS übernimmt TLS auf Port 443.

1. **IIS installieren** (oder `install.ps1 -InstallIIS`):
   ```powershell
   Install-WindowsFeature Web-Server, Web-WebSockets -IncludeManagementTools
   ```
2. **Module installieren** (Microsoft-Downloads, MSI):
   * URL Rewrite 2.1 – <https://www.iis.net/downloads/microsoft/url-rewrite>
   * Application Request Routing 3.0 – <https://www.iis.net/downloads/microsoft/application-request-routing>
3. **Proxy aktivieren:** IIS-Manager → Server-Knoten → *Application Request Routing Cache* →
   *Server Proxy Settings* → **Enable proxy** anhaken. „Reverse rewrite host in response headers“ **deaktivieren**.
   Per PowerShell:
   ```powershell
   Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter 'system.webServer/proxy' -Name enabled -Value True
   Set-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Filter 'system.webServer/proxy' -Name reverseRewriteHostInResponseHeaders -Value False
   ```
4. **Site anlegen:**
   ```powershell
   New-Item -ItemType Directory C:\inetpub\cyberlab
   Copy-Item C:\CyberLab\deploy\windows\web.config C:\inetpub\cyberlab\
   New-Website -Name "CyberLab" -PhysicalPath C:\inetpub\cyberlab -Port 80 -HostHeader cyberlab.campus.local
   ```
5. **Zertifikat:** Ein Zertifikat der internen CA (bzw. DFN-PKI/GÉANT TCS über die IT) für
   `cyberlab.campus.local` importieren und im IIS-Manager eine **https-Bindung** (443, SNI) hinzufügen.
6. **Server-Variablen erlauben:** Falls IIS beim Aufruf „HTTP_X_FORWARDED_PROTO not allowed“ meldet:
   IIS-Manager → Site → *URL Rewrite* → *View Server Variables* → beide Variablen hinzufügen.
7. **Firewall:**
   ```powershell
   New-NetFirewallRule -DisplayName "CyberLab HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -Profile Domain
   ```
   Port 8080 wird **nicht** freigegeben.
8. In `C:\CyberLab\instance\config.py`: `SESSION_COOKIE_SECURE = True`, Dienst neu starten:
   `Restart-Service GolmCyberLab`.
