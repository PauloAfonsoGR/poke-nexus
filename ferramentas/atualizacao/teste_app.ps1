# Funções para testar o PokeNexus EMPACOTADO como uma pessoa usaria (só para os testes de atualização).
#   . ferramentas\atualizacao\teste_app.ps1
#
# Abrir-PokeNexus  abre o .exe com POKENEXUS_DATA (pasta temporária: nenhuma conta real) e a URL falsa
# Print-Janela     print da janela principal (PrintWindow), mesmo atrás de outras janelas
# Clicar           aperta um botão pelo nome (UI Automation: o mesmo clique de uma pessoa)
# Log-Atualizacao  as linhas "Sistema - atualização: ..." do log do dia
# Fechar-PokeNexus fecha no X e confere que não sobrou processo
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class Janela {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
}
"@

function Abrir-PokeNexus([string]$Exe, [string]$Dados, [string]$Url = "") {
    $psi = New-Object Diagnostics.ProcessStartInfo $Exe
    $psi.UseShellExecute = $false
    $psi.EnvironmentVariables["POKENEXUS_DATA"] = $Dados
    if ($Url) { $psi.EnvironmentVariables["POKENEXUS_ATUALIZACAO_URL"] = $Url }
    [Diagnostics.Process]::Start($psi)
}

function Janela-De($proc) {
    for ($i = 0; $i -lt 60; $i++) {
        $proc.Refresh()
        if ($proc.MainWindowHandle -ne [IntPtr]::Zero) { return $proc.MainWindowHandle }
        Start-Sleep -Milliseconds 500
    }
    throw "a janela do PokeNexus não apareceu"
}

function Print-Janela($proc, [string]$Arquivo) {
    $h = Janela-De $proc
    $r = New-Object Janela+RECT
    [Janela]::GetWindowRect($h, [ref]$r) | Out-Null
    $bmp = New-Object Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $g = [Drawing.Graphics]::FromImage($bmp)
    $dc = $g.GetHdc()
    [Janela]::PrintWindow($h, $dc, 2) | Out-Null          # PW_RENDERFULLCONTENT
    $g.ReleaseHdc($dc); $g.Dispose()
    $bmp.Save($Arquivo, [Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
}

function Botoes($proc) {
    $raiz = [Windows.Automation.AutomationElement]::FromHandle((Janela-De $proc))
    $cond = New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ControlTypeProperty),
                                                             ([Windows.Automation.ControlType]::Button)
    $raiz.FindAll([Windows.Automation.TreeScope]::Descendants, $cond)
}

function Clicar($proc, [string]$Nome) {
    # procura na janela principal e nas janelas de diálogo do mesmo processo
    $todas = [Windows.Automation.AutomationElement]::RootElement.FindAll([Windows.Automation.TreeScope]::Children,
        (New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ProcessIdProperty), $proc.Id))
    foreach ($j in $todas) {
        $cond = New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ControlTypeProperty),
                                                                 ([Windows.Automation.ControlType]::Button)
        foreach ($b in $j.FindAll([Windows.Automation.TreeScope]::Descendants, $cond)) {
            if ($b.Current.Name.Trim() -eq $Nome -and $b.Current.IsOffscreen -eq $false) {
                $b.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
                return $true
            }
        }
    }
    return $false
}

function Visivel($proc, [string]$Nome) {
    foreach ($b in (Botoes $proc)) { if ($b.Current.Name.Trim() -eq $Nome -and -not $b.Current.IsOffscreen) { return $true } }
    return $false
}

function Log-Atualizacao([string]$Dados) {
    Get-ChildItem (Join-Path $Dados "logs") -Filter *.log -ErrorAction SilentlyContinue |
        ForEach-Object { Get-Content $_.FullName -Encoding UTF8 } | Where-Object { $_ -match "atualiza" }
}

Add-Type -Namespace PN -Name Fim -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr SendMessageTimeout(IntPtr h, uint msg, IntPtr w, IntPtr l,
    uint flags, uint ms, out IntPtr r);
'@

function Fechar-PokeNexus($proc) {
    # O X só deixa na bandeja: fecha de verdade pelo fim de sessão (WM_QUERYENDSESSION/WM_ENDSESSION, o
    # mesmo caminho do Sair que o instalador usa).
    $pasta = Split-Path $proc.Path
    if (-not $proc.HasExited) {
        $proc.Refresh()
        $h = $proc.MainWindowHandle
        $proc.CloseMainWindow() | Out-Null
        if (-not $proc.WaitForExit(5000) -and $h -ne [IntPtr]::Zero) {
            $r = [IntPtr]::Zero
            [PN.Fim]::SendMessageTimeout($h, 0x11, [IntPtr]::Zero, [IntPtr]1, 2, 60000, [ref]$r) | Out-Null
            [PN.Fim]::SendMessageTimeout($h, 0x16, [IntPtr]1, [IntPtr]1, 2, 60000, [ref]$r) | Out-Null
        }
        $proc.WaitForExit(30000) | Out-Null
    }
    Start-Sleep 2
    @(Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($pasta, [StringComparison]::OrdinalIgnoreCase) })
}
