param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$JavaHome = 'C:\Program Files\Java\jdk-21.0.12.1'
)

$ErrorActionPreference = 'Stop'
$python = Join-Path $ProjectRoot '.venv_new\Scripts\python.exe'
$sparkSubmit = Join-Path $ProjectRoot '.venv_new\Scripts\spark-submit.cmd'
$pysparkHome = Join-Path $ProjectRoot '.venv_new\Lib\site-packages\pyspark'

foreach ($requiredPath in @(
    (Join-Path $JavaHome 'bin\java.exe'),
    $python,
    $sparkSubmit,
    (Join-Path $pysparkHome 'jars')
)) {
    if (-not (Test-Path $requiredPath)) {
        throw "Required Spark/Java path was not found: $requiredPath"
    }
}

$env:JAVA_HOME = (Resolve-Path $JavaHome).Path
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
$env:SPARK_HOME = (Resolve-Path $pysparkHome).Path
$env:PYSPARK_PYTHON = (Resolve-Path $python).Path
$env:PYSPARK_DRIVER_PYTHON = $env:PYSPARK_PYTHON

& $python (Join-Path $ProjectRoot 'backend\jobs\check_als_environment.py')
if ($LASTEXITCODE -ne 0) {
    throw 'Spark environment preflight failed.'
}

& $sparkSubmit --master 'local[2]' (Join-Path $ProjectRoot 'backend\jobs\test_als_smoke.py')
if ($LASTEXITCODE -ne 0) {
    throw 'Synthetic ALS smoke test failed.'
}
