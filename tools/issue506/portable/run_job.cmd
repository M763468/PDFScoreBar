@echo off
rem Issue #506 PoC launcher for a relocated portable folder. Not a product launcher.
rem Usage: run_job.cmd <input.pdf> <output-root> [pages...]
setlocal
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
for /d %%P in ("%ROOT%\python\cpython-3.12.*") do set "BASEPY=%%P\python.exe"
"%BASEPY%" -I "%ROOT%\app\tools\issue506\portable\materialize.py" "%ROOT%" || exit /b 2
set "PYTHONPATH=%ROOT%\shim;%ROOT%\app"
set "PYTHONUTF8=1"
set "PDFSCOREBAR_MODEL_CACHE=%ROOT%\assets\model-cache"
set "PDFSCORE_REALESRGAN_WEIGHTS_DIR=%ROOT%\assets\realesrgan"
set "PDFSCORE_LABEL_FONT=%ROOT%\assets\fonts\DejaVuSans-Bold.ttf"
set "TORCHINDUCTOR_CACHE_DIR=%ROOT%\cache\inductor"
set "TRITON_CACHE_DIR=%ROOT%\cache\triton"
set "TORCH_HOME=%ROOT%\cache\torch"
set "HF_HOME=%ROOT%\cache\hf"
set "TEMP=%ROOT%\cache\tmp"
set "TMP=%ROOT%\cache\tmp"
if not exist "%TEMP%" mkdir "%TEMP%"
set "PDF=%~1"
set "OUT=%~2"
shift
shift
set "PAGES="
:collect
if "%~1"=="" goto run
set "PAGES=%PAGES% %~1"
shift
goto collect
:run
pushd "%ROOT%\app"
if defined PAGES (
  "%ROOT%\venv\Scripts\python.exe" -m docker.distribution_job "%PDF%" --output "%OUT%" --pages%PAGES%
) else (
  "%ROOT%\venv\Scripts\python.exe" -m docker.distribution_job "%PDF%" --output "%OUT%"
)
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
