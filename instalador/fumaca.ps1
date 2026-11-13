# Trava 2 do build (teste de fumaça): o PokeNexus empacotado abre, fica de pé e fecha sem sobrar processo.
# Usado pelo GitHub Actions antes de publicar e dá para rodar à mão:
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File instalador\fumaca.ps1 [-Exe dist\PokeNexus\PokeNexus.exe]
#
# Pasta de dados temporária (POKENEXUS_DATA): nenhuma conta e nenhum dado do usuário é tocado.
param(
    [string]$Exe = "dist\PokeNexus\PokeNexus.exe",
    [int]$Segundos = 25
)
$ErrorActionPreference = "Stop"
$exe = (Resolve-Path $Exe).Path
$pasta = Split-Path $exe
$dados = Join-Path ([IO.Path]::GetFullPath($env:TEMP)) ("pn_fumaca_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory $dados | Out-Null

function Do-Pacote { @(Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($pasta, [StringComparison]::OrdinalIgnoreCase) }) }

$psi = New-Object Diagnostics.ProcessStartInfo $exe
$psi.UseShellExecute = $false
$psi.EnvironmentVariables["POKENEXUS_DATA"] = $dados
$p = [Diagnostics.Process]::Start($psi)
Write-Host "PokeNexus aberto (PID $($p.Id)); esperando $Segundos s..."
Start-Sleep -Seconds $Segundos
$falhas = @()
if ($p.HasExited) { $falhas += "o processo fechou sozinho (código $($p.ExitCode))" }
$crash = Join-Path $dados "logs\crash.log"
if (Test-Path $crash) { $falhas += "apareceu logs\crash.log:`n" + (Get-Content $crash -Raw) }

Add-Type -Namespace PN -Name Janela -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern IntPtr SendMessageTimeout(IntPtr h, uint msg, IntPtr w, IntPtr l,
    uint flags, uint ms, out IntPtr r);
'@
if (-not $p.HasExited) {
    # O X da janela (WM_CLOSE) deixa o PokeNexus na bandeja, com as contas rodando. Fechar de verdade é pelo
    # Sair (MainWindow.sair), que o fim de sessão do Windows e o instalador também usam: WM_QUERYENDSESSION e
    # WM_ENDSESSION com ENDSESSION_CLOSEAPP, como o Restart Manager manda. Sem bandeja na sessão, o X fecha.
    # Sem janela à vista (sessão sem área de trabalho), encerra a árvore.
    $p.Refresh()
    $h = $p.MainWindowHandle
    $fechou = $p.CloseMainWindow()
    if ($fechou -and -not $p.WaitForExit(10000)) {
        if ([PN.Janela]::IsWindowVisible($h)) { $falhas += "o X não escondeu a janela" }
        Write-Host "o X deixou o PokeNexus na bandeja; fechando pelo fim de sessão (o caminho do Sair)"
        $r = [IntPtr]::Zero
        [PN.Janela]::SendMessageTimeout($h, 0x11, [IntPtr]::Zero, [IntPtr]1, 2, 60000, [ref]$r) | Out-Null
        [PN.Janela]::SendMessageTimeout($h, 0x16, [IntPtr]1, [IntPtr]1, 2, 60000, [ref]$r) | Out-Null
    }
    if (-not $p.WaitForExit(30000)) {
        if ($fechou) { $falhas += "não fechou em 30 s pelo caminho do Sair" }
        Write-Host "sem janela para fechar: encerrando a árvore do processo"
        taskkill /PID $p.Id /T /F | Out-Null
        $p.WaitForExit(15000) | Out-Null
    }
}
Start-Sleep -Seconds 3
$sobra = Do-Pacote
if ($sobra.Count) { $falhas += "sobrou processo: " + (($sobra | ForEach-Object { "$($_.Name) ($($_.Id))" }) -join ", "); $sobra | Stop-Process -Force }
Remove-Item -Recurse -Force $dados -ErrorAction SilentlyContinue

if ($falhas.Count) {
    Write-Host "FUMAÇA FALHOU:"; $falhas | ForEach-Object { Write-Host " - $_" }
    exit 1
}
Write-Host "Fumaça ok: abriu, ficou $Segundos s de pé, sem crash.log, fechou pelo Sair e não sobrou processo."
exit 0
