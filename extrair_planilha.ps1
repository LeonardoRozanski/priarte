# Extrai o conteudo de um .xlsx para CSVs (sem depender de Python/Excel)
param(
    [string]$XlsxPath = (Join-Path $PSScriptRoot 'planilha_original.xlsx'),
    [string]$OutDir = (Join-Path $PSScriptRoot 'extracao')
)

Add-Type -AssemblyName System.IO.Compression.FileSystem

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

$zip = [System.IO.Compression.ZipFile]::OpenRead($XlsxPath)

function Read-EntryText($entry) {
    $reader = New-Object System.IO.StreamReader($entry.Open(), [System.Text.Encoding]::UTF8)
    $text = $reader.ReadToEnd()
    $reader.Close()
    return $text
}

# --- shared strings ---
$shared = @()
$ssEntry = $zip.Entries | Where-Object { $_.FullName -eq 'xl/sharedStrings.xml' }
if ($ssEntry) {
    [xml]$ssXml = Read-EntryText $ssEntry
    $ns = New-Object System.Xml.XmlNamespaceManager($ssXml.NameTable)
    $ns.AddNamespace('m', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main')
    foreach ($si in $ssXml.SelectNodes('//m:si', $ns)) {
        $texts = $si.SelectNodes('.//m:t', $ns) | ForEach-Object { $_.'#text' }
        $shared += ($texts -join '')
    }
}
Write-Host "SharedStrings: $($shared.Count)"

# --- workbook: nomes das abas ---
[xml]$wbXml = Read-EntryText ($zip.Entries | Where-Object { $_.FullName -eq 'xl/workbook.xml' })
$nsWb = New-Object System.Xml.XmlNamespaceManager($wbXml.NameTable)
$nsWb.AddNamespace('m', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main')
$nsWb.AddNamespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')

[xml]$relsXml = Read-EntryText ($zip.Entries | Where-Object { $_.FullName -eq 'xl/_rels/workbook.xml.rels' })
$relMap = @{}
foreach ($rel in $relsXml.Relationships.Relationship) {
    $relMap[$rel.Id] = $rel.Target
}

function ColToIndex([string]$col) {
    $idx = 0
    foreach ($ch in $col.ToCharArray()) { $idx = $idx * 26 + ([int][char]$ch - 64) }
    return $idx - 1
}

foreach ($sheet in $wbXml.SelectNodes('//m:sheets/m:sheet', $nsWb)) {
    $name = $sheet.name
    $rid = $sheet.GetAttribute('id', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
    $target = $relMap[$rid]
    if (-not $target.StartsWith('xl/')) { $target = 'xl/' + $target }

    [xml]$shXml = Read-EntryText ($zip.Entries | Where-Object { $_.FullName -eq $target })
    $nsS = New-Object System.Xml.XmlNamespaceManager($shXml.NameTable)
    $nsS.AddNamespace('m', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main')

    $rowsOut = New-Object System.Collections.Generic.List[string]
    foreach ($row in $shXml.SelectNodes('//m:sheetData/m:row', $nsS)) {
        $cells = @{}
        $maxCol = 0
        foreach ($c in $row.SelectNodes('m:c', $nsS)) {
            $ref = $c.r
            $colLetters = ($ref -replace '[0-9]', '')
            $ci = ColToIndex $colLetters
            if ($ci -gt $maxCol) { $maxCol = $ci }
            $t = $c.t
            $vNode = $c.SelectSingleNode('m:v', $nsS)
            $isNode = $c.SelectSingleNode('m:is', $nsS)
            $val = ''
            if ($t -eq 's' -and $vNode) {
                $val = $shared[[int]$vNode.InnerText]
            } elseif ($t -eq 'inlineStr' -and $isNode) {
                $texts = $isNode.SelectNodes('.//m:t', $nsS) | ForEach-Object { $_.'#text' }
                $val = ($texts -join '')
            } elseif ($vNode) {
                $val = $vNode.InnerText
            }
            $cells[$ci] = $val
        }
        $line = for ($i = 0; $i -le $maxCol; $i++) {
            $v = $cells[$i]
            if ($null -eq $v) { $v = '' }
            $v = $v -replace '"', '""'
            if ($v -match '[",;`n`r]') { '"' + $v + '"' } else { $v }
        }
        $rowsOut.Add(($line -join ';'))
    }

    $safeName = ($name -replace '[\\/:*?"<>|]', '_')
    $outPath = Join-Path $OutDir ("$safeName.csv")
    [System.IO.File]::WriteAllLines($outPath, $rowsOut, (New-Object System.Text.UTF8Encoding $true))
    Write-Host "Aba '$name' -> $outPath ($($rowsOut.Count) linhas)"
}

$zip.Dispose()
Write-Host 'Concluido.'
