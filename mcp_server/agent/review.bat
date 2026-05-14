@echo off
cd /d C:\Users\hbset\elixirx-portal
call backend\venv\Scripts\activate
python -m mcp_server.agent.reviewer
pause
