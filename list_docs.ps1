# ------------------------------------------------------------
# List documentation-related files (.md, .txt, .rst)
# and save them to a single text file
# ------------------------------------------------------------

$OutputFile = "documentation_files.txt"

Get-ChildItem -Recurse -File |
Where-Object {
    $_.Extension -in ".md", ".txt", ".rst"
} |
Sort-Object FullName |
ForEach-Object {
    $_.FullName
} |
Out-File -Encoding UTF8 $OutputFile

Write-Output "Listado generado en $OutputFile"
