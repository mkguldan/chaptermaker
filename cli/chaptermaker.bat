@echo off
REM Video Chapter Maker CLI for Windows

REM Get the directory of this batch file
set SCRIPT_DIR=%~dp0

REM Run the Python script with all arguments
python "%SCRIPT_DIR%chaptermaker-cli.py" %*
