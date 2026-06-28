Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d C:\dev\AI-VIDEO-MAKER\backend && venv\Scripts\uvicorn main:app --port 8000", 0, false
WshShell.Run "cmd /c cd /d C:\dev\AI-VIDEO-MAKER\frontend && npm run dev -- --port 3001", 0, false
