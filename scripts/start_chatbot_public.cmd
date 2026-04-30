@echo off
cd /d "C:\Users\HP\source\repos\Chatbot"
start "" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\HP\source\repos\Chatbot\scripts\run_ngrok_dev.ps1" -NgrokExe "C:\Users\HP\Downloads\ngrok.exe" -FrontendPort 5174