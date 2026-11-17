@echo off
REM ============================================================
REM  F.R.Y.I.Vs - Inicializador
REM  Executar SEMPRE por duplo clique (sessao interativa do usuario),
REM  para que Edge/Chrome/Word/Excel abram VISIVEIS na sua tela.
REM ============================================================
title F.R.Y.I.Vs Server
cd /d "%~dp0"
chcp 65001 >nul

REM Desativa QuickEdit Mode temporariamente no console do Windows para evitar pausas acidentais
powershell -Command "$t = Add-Type -MemberDefinition '[DllImport(\"kernel32.dll\")] public static extern IntPtr GetStdHandle(int n); [DllImport(\"kernel32.dll\")] public static extern bool GetConsoleMode(IntPtr h, out uint m); [DllImport(\"kernel32.dll\")] public static extern bool SetConsoleMode(IntPtr h, uint m);' -Name 'ConsoleQuickEdit' -Namespace 'Win32' -PassThru; $h = $t::GetStdHandle(-10); $m = 0; if ($t::GetConsoleMode($h, [ref]$m)) { $t::SetConsoleMode($h, ($m -band -bnot 0x0040) -bor 0x0080); }" >nul 2>&1

REM Libera a porta 8000 caso exista um servidor antigo
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1

start "" /min cmd /c "timeout /t 6 >nul && start http://127.0.0.1:8000"
"%~dp0venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000
pause
