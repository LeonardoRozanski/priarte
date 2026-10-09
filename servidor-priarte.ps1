# Servidor local da PriArte — gera um link para abrir o app no iPhone/Mac/Android
# na MESMA rede Wi-Fi. Sem internet, sem custo: só o seu PC servindo o arquivo.
# Uso: clique duas vezes (ele vai pedir permissao de Administrador 1 vez para
# liberar a porta) OU rode como Administrador.

# --- auto-elevacao: precisa de admin para abrir a porta HTTP na rede ---
$identidade = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object System.Security.Principal.WindowsPrincipal($identidade)
if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "Pedindo permissao de Administrador para liberar a porta..." -ForegroundColor Yellow
  Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
  exit
}

$porta = 8585
$pastaApp = Join-Path $PSScriptRoot 'app'

# pega o IP REAL da rede (ignora adaptadores virtuais WSL/Hyper-V/VPN/Tailscale)
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
      $_.IPAddress -match '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -and
      $_.InterfaceAlias -notmatch 'WSL|Hyper-V|Default Switch|vEthernet|Tailscale|VPN|Loopback|wt\d' -and
      $_.IPAddress -notmatch '^169\.'
    } |
    Sort-Object { if ($_.InterfaceAlias -match 'Wi-Fi|Wireless') { 0 } else { 1 } } |
    Select-Object -First 1).IPAddress
if (-not $ip) { $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -match '^192\.168\.' } | Select-Object -First 1).IPAddress }

$url = "http://${ip}:$porta/index.html"

Write-Host ""
Write-Host "  ================================================" -ForegroundColor Magenta
Write-Host "   PriArte Atelie - servidor local ligado" -ForegroundColor Magenta
Write-Host "  ================================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Abra este link no CELULAR (mesma rede Wi-Fi):" -ForegroundColor Cyan
Write-Host ""
Write-Host "      $url" -ForegroundColor Yellow
Write-Host ""
Write-Host "  No iPhone: digite esse endereco no Safari." -ForegroundColor White
Write-Host "  Depois: Compartilhar -> Adicionar a Tela de Inicio." -ForegroundColor White
Write-Host ""
Write-Host "  Deixe esta janela ABERTA enquanto usa o app." -ForegroundColor DarkGray
Write-Host "  Para parar: feche a janela ou Ctrl+C." -ForegroundColor DarkGray
Write-Host ""

# ja estamos elevados (auto-elevacao acima): registra URL ACL + firewall de vez
netsh http delete urlacl url=http://+:$porta/ 2>$null | Out-Null
netsh http add urlacl url=http://+:$porta/ user="Todos" 2>$null | Out-Null
netsh http add urlacl url=http://+:$porta/ user="Everyone" 2>$null | Out-Null
netsh advfirewall firewall delete rule name="PriArte $porta" 2>$null | Out-Null
netsh advfirewall firewall add rule name="PriArte $porta" dir=in action=allow protocol=TCP localport=$porta 2>$null | Out-Null

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://+:$porta/")
try { $listener.Start() } catch {
  Write-Host "ERRO ao abrir a porta $porta : $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Feche e rode este script como Administrador (botao direito -> Executar como administrador)." -ForegroundColor Yellow
  pause; exit 1
}

# abre o app no PC tambem (conferencia)
Start-Process "http://localhost:$porta/index.html"

while ($listener.IsListening) {
  try { $ctx = $listener.GetContext() } catch { break }
  $req = $ctx.Request; $res = $ctx.Response
  $caminho = [System.Web.HttpUtility]::UrlDecode($req.Url.LocalPath.TrimStart('/'))
  if ([string]::IsNullOrEmpty($caminho)) { $caminho = 'index.html' }
  # Sirva somente a interface. Planilhas, backups e caminhos externos são privados.
  if ($caminho -notin @('index.html', 'sw.js')) {
    $res.StatusCode = 404
    $res.OutputStream.Close()
    continue
  }
  $arquivo = Join-Path $pastaApp $caminho
  if (Test-Path $arquivo -PathType Leaf) {
    $bytes = [System.IO.File]::ReadAllBytes($arquivo)
    switch ([System.IO.Path]::GetExtension($arquivo).ToLower()) {
      '.html' { $res.ContentType = 'text/html; charset=utf-8' }
      '.js'   { $res.ContentType = 'text/javascript; charset=utf-8' }
      '.json' { $res.ContentType = 'application/json; charset=utf-8' }
      '.webmanifest' { $res.ContentType = 'application/manifest+json' }
      default { $res.ContentType = 'application/octet-stream' }
    }
    $res.ContentLength64 = $bytes.Length
    $res.OutputStream.Write($bytes, 0, $bytes.Length)
  } else {
    $res.StatusCode = 404
    $msg = [System.Text.Encoding]::UTF8.GetBytes('404 - nao encontrado')
    $res.OutputStream.Write($msg, 0, $msg.Length)
  }
  $res.OutputStream.Close()
}
